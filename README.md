# RSImgLazyLoader
A Lazy Loader for Remote Sensing Image

## Key Features
- automatic CRS and projection unification
- block-based lazy loading
- time-series data organization

## Install Requirements
conda
```bash
conda install -c conda-forge gdal rasterio numpy
```
pip
```bash
pip install gdal rasterio numpy
```

## Quick Start
### Import and Create Object
```python
from lazy_loader import LazyLoader
loader = LazyLoader(
  (100, 100)  # block size
) 
```

### Prepare Files
provide dictionary directly
```python
files = {
        datetime.date(2025, 1, 1): "sample1.tif",
        datetime.date(2025, 1, 2): "sample2.tif",
        datetime.date(2025, 1, 3): "sample3.tif",
    }
```
or give a dir (`.tif` support only)
```python
loader.addFilesFromPath(your_path, time_string_slice, time_string_format)
```

### Set Reference
```python
loader.getReferenceFromFiles()
```

### Init
Initialization is **REQUIRED** before get block.
You must initialize after modifying files and reference.
```python
loader.init()
```

### Get Block
```python
for block in loader:
    do_someting()
```

## License
MIT License (c) 2025 Zhao Yuhui
