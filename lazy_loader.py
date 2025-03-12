import os
from dataclasses import dataclass
import datetime
import tempfile

import numpy as np
from osgeo import gdal
import rasterio
from rasterio.warp import calculate_default_transform
from rasterio.windows import Window

@dataclass
class LazyLoaderRefer:
    crs: str
    transform: tuple
    shape: tuple[int, int]
    bounds: tuple[float, float, float, float]
    res: tuple[float, float]


class LazyLoader(object):
    def __init__(self, limit: tuple[int, int]):
        self.limit = limit
        self._reference = None
        self.sig_init: bool = False

        self.files: dict[datetime.date, str] = {}
        self.sorted_files: list[str] = []
        self.vrt_files: list[str] = []

        self.blocks: list[tuple[int, int]] = []

    def addFilesFromPath(self, _path: str, _slice: slice,  _format: str):
        for entry in os.scandir(_path):
            if entry.is_file() and entry.name.endswith('.tif'):
                self.files[datetime.datetime.strptime(entry.name, _format).date()] = entry.path
        self.sig_init = False

    @property
    def reference(self) -> LazyLoaderRefer:
        return self._reference

    def setReference(self, reference: LazyLoaderRefer):
        self._reference = reference

    def getReferenceFromFiles(self):
        # 收集所有文件的crs,并确定目标crs
        crs_list = []
        for path in self.files.values():
            with rasterio.open(path) as src:
                crs_list.append(src.crs)
        target_crs = max(crs_list, key=crs_list.count)

        # 转换所有边界到目标crs
        target_bounds = []
        for path in self.files.values():
            with rasterio.open(path) as src:
                if src.crs != target_crs:
                    transformed_bounds = rasterio.warp.transform_bounds(src.crs, target_crs, *src.bounds)
                else:
                    transformed_bounds = src.bounds
                target_bounds.append(transformed_bounds)

        # 确定目标边界
        all_lefts, all_bottoms, all_rights, all_tops = zip(*target_bounds)
        target_left = min(all_lefts)
        target_bottom = min(all_bottoms)
        target_right = max(all_rights)
        target_top = max(all_tops)

        # 确定分辨率（使用第一个影像）
        with rasterio.open(list(self.files.values())[0]) as src:
            res = src.res

        # 统一transform和shape
        transform = rasterio.transform.from_origin(target_left, target_top, res[0], res[1])
        width = int((target_right - target_left) / res[0])
        height = int((target_top - target_bottom) / res[1])

        self.sig_init = False
        self._reference = LazyLoaderRefer(
            target_crs if isinstance(target_crs, str) else target_crs.to_string(),
            transform,
            (width, height),
            (target_left, target_bottom, target_right, target_top),
            res
        )

    def init(self):
        if self.reference is None:
            raise RuntimeError(f"RSDataLazyLoader requires a reference before init")
        if self.files is None:
            raise RuntimeError(f"RSDataLazyLoader requires a list of files before init")

        # 排序
        self.sorted_files = sorted(self.files)

        # 创建vrt数据集
        for path in self.files.values():
            vrt_path = os.path.join(tempfile.gettempdir(), os.path.basename(path) + ".vrt")
            ds = gdal.Open(path)
            warp_options = gdal.WarpOptions(
                format='VRT',
                dstSRS=self.reference.crs,
                outputBounds=self.reference.bounds,
                xRes=self.reference.res[0],
                yRes=self.reference.res[1],
                resampleAlg=gdal.GRA_NearestNeighbour
            )
            vrt_ds = gdal.Warp(vrt_path, ds, options=warp_options)
            vrt_ds.FlushCache()
            self.vrt_files.append(vrt_path)
            del vrt_ds, ds

        # 计算分块
        width, height = self.reference.shape
        x_blocks = (width + self.limit[0] - 1) // self.limit[0] # todo
        y_blocks = (height + self.limit[1] - 1) // self.limit[1]
        self.blocks = [(x, y) for x in range(x_blocks) for y in range(y_blocks)]

        self.sig_init = True

    def getWindow(self, index: tuple[int, int]):
        x_start = index[0] * self.limit[0]
        y_start = index[1] * self.limit[1]
        x_size = min(self.limit[0], self.reference.shape[0] - x_start)
        y_size = min(self.limit[1], self.reference.shape[1] - y_start)
        return Window(x_start, y_start, x_size, y_size)

    def getBlock(self, index: tuple[int, int]):
        if not self.sig_init:
            raise RuntimeError(f"RSDataLazyLoader requires init before getBlock")

        time_series = []
        for vrt_file in self.vrt_files:
            with rasterio.open(vrt_file) as src:
                data = src.read(window=self.getWindow(index))
                time_series.append(data)
        return np.array(time_series)

    def __iter__(self):
        for x, y in self.blocks:
            yield self.getBlock((x,y))

    def __del__(self):
        for vrt_file in self.vrt_files:
            try:
                os.remove(vrt_file)
            except OSError:
                pass
