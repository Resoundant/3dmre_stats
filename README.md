# 3dmre_stats
Support for 3DMRE research applications.

## 1 - Compute Within-ROI Statistics on mmdi3d Data Processed By Hepatogram Plus
### Dependencies
`numpy`, `pydicom`

### Getting Started
The main function for the task is `measure_mmdi3d_contrasts_in_rois()` in the `mmdi3d_utils.py` module. Its arguments are:
* `alc2_digest:str`: the full file path to the alc2 file for the MRE series you want to analyze.
* `temp_dir:str`: the Hepatogram Plus "temp" directory location. Default value `'default'` will set equal to `alc2_digest`'s parent directory.
* `inversion_3d_dir:str`: the mmdi3d results folder `3dmmdi`. Default value `'default'` will attempt to locate it based on past Hepatogram Plus workflows.
* `exclude_negative_pixels:bool`: A flag to exclude negative pixels from the statistical calculations. Default value is `False`.
* `logger:str`: Optional argument for a python logger object. Default value is `'None'`.

`measure_mmdi3d_contrasts_in_rois()` will return a 2-tuple. The return arguments are:
* A `dict` containing ROI and contrast file path locations and `SliceLocation`'s, according to slice numbers.
* A `dict` of the within-ROI statistical values as `str` objects keyed by contrast name.

### Modifying Statistical Calculations
The function where the statistics are calculated is `apply_rois_to_mmdi3d_contrasts()` in the `mmdi3d_utils.py` module. The `dict` variable `contrast_data` is where results are stored. In its initial definition, modify the list of statistics that you want calculated. Then modify the statistical computation parts of the code below to add the appropriate dictionary elements.
