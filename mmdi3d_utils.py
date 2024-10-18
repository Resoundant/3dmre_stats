"""
mmdi3d_utils.py
Functions for supporting mmdi3d in Hepatogram Plus
"""
import os, numpy as np
from pydicom import read_file
from os_utils import dir_folder_list, dir_file_list, os_clean_path, path_split, run_cmd_with_logging
from dicom_and_file_utils import read_images, parse_digest
CONTRASTS={'storage':'26',
           'loss':'27',
           'attenuation':'28',
           'damping_ratio':'',
           'volumetric_strain':''}

def add_to_log(message:str,logger:str='None'):
    """
    add_to_log():
    Adds message to logger object if logger!='None'
    Otherwise prints message to console
    """
    if logger!='None':
        logger.info(message)
    else:
        print(message)
    return

def find_mmdi3d_datasets(top_dir:str,rapid:bool=False,logger:str='None')->dict:
    """
    find_mmdi3d_datasets():
    Searches top_dir for mmdi3d datasets
    Returns dict data3d containing under key 'data' dataset folders and series numbers
    Assumes a valid DICOM in a folder can represent the entire folder
    If rapid=True, checks only the first file in the folder
    If rapid=False, checks every file in the folder
    """
    #Initializing
    data3d={'top_dir':top_dir,
            'Manufacturer':'',
            'data':[]}

    #Searching for mmdi3d datasets top_dir
    add_to_log('find_mmdi3d_datasets(): Searching for mmdi3d datasets '+top_dir,logger)
    for folder in dir_folder_list(top_dir):
        #Counting valid DICOM files in folder and opening one for data parsing
        file_list=dir_file_list(os.path.join(top_dir,folder),include_dir=True)
        dcm_count=0

        #Rapid but less reliable method
        if rapid:
            try:
                dcm=read_file(file_list[0],stop_before_pixels=True)
            except:
                continue
            else:
                dcm_count=len(file_list)

        #Slow but careful method
        else:
            for file_path in file_list:
                try:
                    dcm=read_file(file_path,stop_before_pixels=True)
                except:
                    continue
                else:
                    dcm_count=dcm_count+1
            
            #Warning if dcm_count not the same as folder file count
            if dcm_count!=len(file_list):
                add_to_log('WARNING find_mmdi3d_datasets(): dcm_count='+str(dcm_count)+' but '+str(len(file_list))+' total files in '+os.path.join(top_dir,folder),logger)
        
        #Skipping invalid folder
        if (dcm_count==0) or ('SeriesDescription' not in dcm) or ('Manufacturer' not in dcm) or ('3d-mmdi' in dcm.get('SequenceName','')):
            continue
        
        #Getting Manufacturer
        if 'siemens' in dcm.Manufacturer.lower():
            data3d['Manufacturer']='Siemens'
        elif 'philips' in dcm.Manufacturer.lower():
            data3d['Manufacturer']='Philips'
        elif 'ge' in dcm.Manufacturer.lower():
            data3d['Manufacturer']='GE'

        #Checking for manufacturer validity
        ge_valid_like=(data3d['Manufacturer']=='GE') and ('MRE' in dcm.SeriesDescription) and (dcm_count>800)
        siemens_valid_like=(data3d['Manufacturer']=='Siemens') and ('928' in dcm.SeriesDescription) and ('3D' in dcm.SeriesDescription)
        philips_valid_like=(data3d['Manufacturer']=='Philips') and (dcm_count>280)
        
        #Adding metadata to data3d
        if ge_valid_like or philips_valid_like:
            data3d['data'].append({'mag':folder,'mag_series':dcm.SeriesNumber})
        
        #Treating Siemens separately for mag and phase
        elif siemens_valid_like:
            if dcm.SeriesDescription.lower().endswith('mag'):
                #Checking if phase data already added
                for i in range(len(data3d['data'])):
                    if ('phase_series' in data3d['data'][i].keys()) and (data3d['data'][i]['phase_series']==dcm.SeriesNumber+1):
                        data3d['data'][i]['mag']=folder
                        data3d['data'][i]['mag_series']=dcm.SeriesNumber
                        break
                
                #Creating new entry if no phase data
                if (len(data3d['data'])==0) or ((i==len(data3d['data'])-1) and ('mag' not in data3d['data'][i].keys())):
                    data3d['data'].append({'mag':folder,'mag_series':dcm.SeriesNumber})
            
            elif dcm.SeriesDescription.lower().endswith('p_p'):
                #Checking if mag data already added
                for i in range(len(data3d['data'])):
                    if ('mag_series' in data3d['data'][i].keys()) and (data3d['data'][i]['mag_series']==dcm.SeriesNumber-1):
                        data3d['data'][i]['phase']=folder
                        data3d['data'][i]['phase_series']=dcm.SeriesNumber
                        break
                
                #Creating new entry if no mag data
                if (len(data3d['data'])==0) or ((i==len(data3d['data'])-1) and ('phase' not in data3d['data'][i].keys())):
                    data3d['data'].append({'phase':folder,'phase_series':dcm.SeriesNumber})
            
            else:
                add_to_log('WARNING find_mmdi3d_datasets(): Siemens-like data found but no mag or phase identified for '+folder,logger)
    
    #Returning results
    return data3d

def get_mmdi3d_freq(mag_dir:str,logger:str='None')->str:
    """
    get_mmdi3d_freq():
    Attempts to find mmdi3d frequency in tag SeriesDescription of first DICOM in mag_dir
    Pads series_desc with 'mre' to guarantee non-numeric string boundary
    If unsuccessful, will give WARNING and return default value '60'
    """
    #Reading in first available DICOM
    freq='60'
    could_not_read_dcm=True
    for file in next(os.walk(mag_dir))[2]:
        file_path=os.path.join(mag_dir,file)
        try:
            dcm=read_file(file_path)
        except:
            continue
        else:
            could_not_read_dcm=False
            break
    
    #WARNING if no DICOM could be read
    if could_not_read_dcm:
        add_to_log('WARNING get_mmdi3d_freq(): could not determine mmdi3d frequency from directory '+str(mag_dir)+', assuming 60Hz',logger)
    
    #Attemping to get frequency from DICOM tag SeriesDescription in dcm
    else:
        series_desc=str(dcm.get('SeriesDescription','')).lower().replace('-','').replace('_','')
        could_not_find_freq=True
        if 'hz' in series_desc:
            series_desc='mre'+series_desc.split('hz')[0].strip()
            for i in range(1,len(series_desc)+1):
                if not series_desc[-i:].strip().isnumeric():
                    freq=series_desc[-i+1:].strip()
                    add_to_log('get_mmdi3d_freq(): Found mmdi3d frequency '+freq+'Hz',logger)
                    could_not_find_freq=False
                    break

        if could_not_find_freq:
            add_to_log('WARNING get_mmdi3d_freq(): could not determine mmdi3d frequency from SeriesDescription of '+file_path+', assuming 60Hz',logger)

    #Returning output
    return freq

def run_mmdi3d_series(exe_mmdi3d:str,manufacturer:str,top_dir:str,dataset:dict,series_dir:str,logger:str='None')->int:
    """
    run_mmdi3d_series():
    Sets up mmdi3d command str cmd using arguments str args_mmdi3d
    Runs cmd with cwd set to the exe_mmdi3d directory
    Returns int exit_code of execution
    """
    #Defining initial mmdi3d arguments
    args_mmdi3d='+liver +dicom +mag-out +pdif-out +save-checker +save-div +save-atten +verbosity 2 +max-threads 3 +file-indir '+top_dir

    #Adding input data format information
    if manufacturer=='GE':
        if 'mag' not in dataset.keys():
            add_to_log("WARNING run_mmdi3d_series(): "+manufacturer+" dataset has no 'mag' key\n"+str(dataset),logger)
        args_mmdi3d+=' +iq-dir '+dataset['mag']
    elif manufacturer=='Philips':
        if 'mag' not in dataset.keys():
            add_to_log("WARNING run_mmdi3d_series(): "+manufacturer+" dataset has no 'mag' key\n"+str(dataset),logger)
        args_mmdi3d+=' +time-direction 1 +mp-dir '+dataset['mag']
    elif manufacturer=='Siemens':
        if 'mag' not in dataset.keys():
            add_to_log("WARNING run_mmdi3d_series(): "+manufacturer+" dataset has no 'mag' key\n"+str(dataset),logger)
        if 'phase' not in dataset.keys():
            add_to_log("WARNING run_mmdi3d_series(): "+manufacturer+" dataset has no 'phase' key\n"+str(dataset),logger)
        args_mmdi3d+=' +time-direction 1 +mag-time-dir '+dataset['mag']+' +phs-dir '+dataset['phase']
    args_mmdi3d+=' +log-dir '+series_dir+' +log-file mmdi3d.log'

    #Adding frequency information
    freq=get_mmdi3d_freq(os.path.join(top_dir,dataset['mag']),logger)
    if freq!='60':
        args_mmdi3d+=' +hz '+freq
    
    #Running command
    cmd=exe_mmdi3d+' '+args_mmdi3d
    add_to_log(cmd,logger)
    exit_code=run_cmd_with_logging(cmd=cmd,cwd=os.path.dirname(exe_mmdi3d),logger=logger)
    return exit_code

def run_mmdi3d_case(exe_mmdi3d:str,inversion_3d_dir:str,data3d:dict,logger:str='None')->list:
    """
    run_mmdi3d_case():
    Checks for non-empty find_mmdi3d_datasets() output data3d giving 3D MRE data digest of a case folder
    If data3d non-empty, runs exe_mmdi3d on each series dataset in data3d and puts results in inversion_3d_dir
    Returns list series_dirs of successful series subdirectories
    """
    #Initializing
    series_dirs=[]

    #Checking for empty data3d
    if (not data3d) or (not data3d.get('data')):
        add_to_log('WARNING run_mmdi3d_case(): no 3D MRE data found in data3d, no mmdi3d inversions computed',logger)
        return series_dirs
    
    #Running mmdi3d on found data
    for dataset in data3d['data']:
        series_dir=os.path.join(inversion_3d_dir,str(dataset['mag_series']))
        exit_code=run_mmdi3d_series(exe_mmdi3d=exe_mmdi3d,
                                    manufacturer=data3d['Manufacturer'],
                                    top_dir=data3d['top_dir'],
                                    dataset=dataset,
                                    series_dir=series_dir,
                                    logger=logger)
        
        #Processing successful
        if exit_code==0:
            add_to_log('run_mmdi3d_case(): Appending to successful series_dirs '+series_dir)
            series_dirs.append(series_dir)
        
        #Processing failed
        else:
            add_to_log('WARNING run_mmdi3d_case(): Unsuccessful 3DDI on '+series_dir)
    
    #Returning results
    return series_dirs

def get_mmdi3d_slice_data(alc2_digest:str,temp_dir:str='default',inversion_3d_dir:str='default',logger:str='None')->dict:
    """
    get_mmdi3d_slice_data():
    Uses alc2_digest to determine the MRE slice numbers, corresponding magnitude images, and SliceLocation of each
    Returns dict slice_data containing ROI and contrast paths and SliceLocation, according to slice_number
    The default temp_dir is the location of the alc2_digest
    The default inversion_3d_dir is the '3dmmdi' folder 3 directories up from the alc2_digest (expected to be the case input_dir)
    If the default inversion_3d_dir is not found, other candidates are tried from legacy versions of hepplus-3d
    """
    #Initializing
    slice_data=dict()
    
    #Validating alc2 digest
    if not alc2_digest.lower().endswith('.alc2'):
        add_to_log('ERROR get_mmdi3d_slice_data(): alc2_digest '+str(alc2_digest)+' does not have .alc2 extension, returning empty dict',logger)
        return slice_data
    elif not os.path.exists(alc2_digest):
        add_to_log('ERROR get_mmdi3d_slice_data(): alc2_digest '+str(alc2_digest)+' does not exist, returning empty dict',logger)
        return slice_data
    elif not os.path.isfile(alc2_digest):
        add_to_log('ERROR get_mmdi3d_slice_data(): alc2_digest '+str(alc2_digest)+' invalid, returning empty dict',logger)
        return slice_data
    content,comments=parse_digest(alc2_digest)

    #Setting temp_dir
    if temp_dir=='default':
        temp_dir=os.path.dirname(alc2_digest)
    elif not os.path.exists(temp_dir):
        add_to_log('ERROR get_mmdi3d_slice_data(): temp_dir '+str(temp_dir)+' does not exist, returning empty dict',logger)
        return slice_data
    elif not os.path.isdir(temp_dir):
        add_to_log('ERROR get_mmdi3d_slice_data(): temp_dir '+str(temp_dir)+' invalid, returning empty dict',logger)
        return slice_data
    
    #Setting inversion_3d_dir
    if inversion_3d_dir=='default':
        candidate_inversion_3d_dirs=[os.path.join(path_split(alc2_digest,3)[0],'3dmmdi'), #input_dir/3dmmdi
                                     os.path.join(path_split(alc2_digest,2)[0],'3dmmdi')  #hepplus_dir/3dmmdi
                                    ]
        for candidate_dir in candidate_inversion_3d_dirs:
            if os.path.exists(candidate_dir) and os.path.isdir(candidate_dir):
                inversion_3d_dir=candidate_dir
                break
        if inversion_3d_dir=='default':
            add_to_log('ERROR get_mmdi3d_slice_data(): no default candidate found for inversion_3d_dir, returning empty dict',logger)
            return slice_data
    elif not os.path.exists(inversion_3d_dir):
        add_to_log('ERROR get_mmdi3d_slice_data(): inversion_3d_dir '+str(inversion_3d_dir)+' does not exist, returning empty dict',logger)
        return slice_data
    elif not os.path.isdir(inversion_3d_dir):
        add_to_log('ERROR get_mmdi3d_slice_data(): inversion_3d_dir '+str(inversion_3d_dir)+' invalid, returning empty dict',logger)
        return slice_data
    
    #Scraping data from digest
    for key1 in content.keys():
        #Getting slice data
        if key1.startswith('mre.roi.slice.'):
            #Getting slice number and roi file path
            slice_number=key1.split('mre.roi.slice.')[-1]
            roi_file_name=os.path.basename(os_clean_path(content[key1]))
            roi_file_path=os.path.join(temp_dir,roi_file_name)
            slice_data[slice_number]={'roi_file_path':roi_file_path}|{contrast+'_path':'' for contrast in CONTRASTS.keys() if CONTRASTS[contrast]!=''}

            #Getting SliceLocation
            slice_location=None
            for key2 in content.keys():
                if key2.startswith('mre.mag.slice.'+slice_number):
                    #Find and open magnitude file
                    mag_file_path=os_clean_path(content[key2])
                    candidate_mag_file_paths=[os.path.join(inversion_3d_dir,path_split(mag_file_path,3)[1]),         #as in inversion_3d_dir/7/s700/i025.dcm
                                              os.path.join(inversion_3d_dir,path_split(mag_file_path,2)[1]),         #as in inversion_3d_dir/s700/i025.dcm
                                              os.path.join(path_split(temp_dir,2)[0],path_split(mag_file_path,2)[1]) #as in input_dir/s700/i025.dcm
                                             ]
                    for candidate_path in candidate_mag_file_paths:
                        try:
                            dcm_mag=read_file(candidate_path)
                        except:
                            continue
                        else:
                            slice_location=dcm_mag.get('SliceLocation',None)
                            if slice_location:
                                break
                            else:
                                continue
                    
                    #Exiting loop if SliceLocation found
                    if slice_location:
                        break
                    else:
                        continue
            slice_data[slice_number]['SliceLocation']=slice_location
            if not slice_location:
                add_to_log('WARNING get_mmdi3d_slice_data(): no SliceLocation found for slice_number='+slice_number+' in alc2_digest '+alc2_digest,logger)
        
        #Getting magnitude series base
        elif key1=='mre.mag.seriesNumber':
            mag_series=content[key1]
    
    #Get contrasts parent directory
    contrast_parent_dir=inversion_3d_dir
    for folder in dir_folder_list(inversion_3d_dir):
        if mag_series.startswith(folder):
            contrast_parent_dir=os.path.join(inversion_3d_dir,folder)
            break

    #Adding contrast file paths when SliceLocation is valid
    for slice_number in slice_data.keys():
        if slice_data[slice_number]['SliceLocation']:
            for contrast in CONTRASTS.keys():
                if CONTRASTS[contrast]!='':
                    #Finding contrast directory
                    for folder in dir_folder_list(contrast_parent_dir):
                        if folder.startswith('s') and folder.endswith(CONTRASTS[contrast]) and mag_series.startswith(folder[1:-2]):
                            contrast_dir=os.path.join(contrast_parent_dir,folder)
                            
                            #Finding contrast file path from SliceLocation
                            for contrast_file_path in dir_file_list(contrast_dir,include_dir=True):
                                try:
                                    dcm_contrast=read_file(contrast_file_path)
                                except:
                                    continue
                                else:
                                    slice_location_contrast=dcm_contrast.get('SliceLocation',None)
                                    if slice_location_contrast==slice_data[slice_number]['SliceLocation']:
                                        slice_data[slice_number][contrast+'_path']=contrast_file_path
                                        break
                                    else:
                                        continue
                            if slice_data[slice_number][contrast+'_path']:
                                break
    
    #Returning slice data
    return slice_data

def apply_rois_to_mmdi3d_contrasts(slice_data:dict,exclude_negative_pixels:bool=False,logger:str='None')->dict:
    """
    apply_rois_to_mmdi3d_contrasts():
    For each contrast, computes the slices where ROI and contrast images are defined
    Then applies the ROI to the stack of contrast images and calculates statistical values
    If exclude_negative_pixels=True negative pixels for storage, loss, and attenuation measurements will be excluded
    Returns dict contrast_data of statistical values as str's keyed by contrast type
    """
    #Initializing
    contrast_data={contrast:{'mean':'','stddev':'','median':'','range':''} for contrast in CONTRASTS.keys()}

    #Computing contrast data
    for contrast in contrast_data.keys():
        #Damping ratio
        if contrast=='damping_ratio':
            #Get valid slice paths
            roi_paths,storage_paths,loss_paths=[],[],[]
            for slice_number in slice_data.keys():
                roi_path=slice_data[slice_number]['roi_file_path']
                storage_path=slice_data[slice_number]['storage_path']
                loss_path=slice_data[slice_number]['loss_path']
                if roi_path and storage_path and loss_path:
                    roi_paths.append(roi_path)
                    storage_paths.append(storage_path)
                    loss_paths.append(loss_path)
            
            #Computing values when paths found
            if len(roi_paths)>0:
                #Computing pixel values
                roi_stack=read_images(roi_paths)
                storage_stack=read_images(storage_paths)
                loss_stack=read_images(loss_paths)
                if exclude_negative_pixels:
                    positive_pixels=(storage_stack>=0)&(loss_stack>=0)
                    roi_stack=roi_stack[positive_pixels]
                    storage_stack=storage_stack[positive_pixels]
                    loss_stack=loss_stack[positive_pixels]
                damping_ratio_stack=0.5*np.divide(loss_stack,storage_stack,where=(storage_stack!=0))
                pixel_values=damping_ratio_stack[(roi_stack>0)&np.logical_not(np.isnan(damping_ratio_stack))]
                
                #Computing statistical values
                if pixel_values.size>0:
                    contrast_data[contrast]['mean']=str(np.round(np.mean(pixel_values),2))
                    contrast_data[contrast]['stddev']=str(np.round(np.std(pixel_values),2))
                    contrast_data[contrast]['median']=str(np.round(np.median(pixel_values),2))
                    contrast_data[contrast]['range']=str(np.round(np.percentile(pixel_values,25),2))+' - '+str(np.round(np.percentile(pixel_values,75),2))
                else:
                    add_to_log('WARNING apply_rois_to_mmdi3d_contrasts(): no valid pixels for '+contrast+', returning null output',logger)
            
            #Warning user when no image paths found
            else:
                add_to_log('WARNING apply_rois_to_mmdi3d_contrasts(): no slices have all required image paths for '+contrast+', returning null output',logger)
        
        #Volumetric strain
        elif contrast=='volumetric_strain':
            continue
        
        #Storage, loss, and attenuation
        else:
            #Get valid slice paths
            roi_paths,contrast_paths=[],[]
            for slice_number in slice_data.keys():
                roi_path=slice_data[slice_number]['roi_file_path']
                contrast_path=slice_data[slice_number][contrast+'_path']
                if roi_path and contrast_path:
                    roi_paths.append(roi_path)
                    contrast_paths.append(contrast_path)
            
            #Computing values when paths found
            if len(roi_paths)>0:
                #Computing pixel values
                roi_stack=read_images(roi_paths)
                contrast_stack=read_images(contrast_paths)
                if exclude_negative_pixels:
                    positive_pixels=(contrast_stack>=0)
                    roi_stack=roi_stack[positive_pixels]
                    contrast_stack=contrast_stack[positive_pixels]
                pixel_values=contrast_stack[roi_stack>0]

                #Computing statistical values
                if pixel_values.size>0:
                    #Rescaling units
                    if contrast in ['storage','loss']:
                        pixel_values=(1e-3)*pixel_values
                    elif contrast in ['attenuation']:
                        pixel_values=(1e-4)*pixel_values
                    contrast_data[contrast]['mean']=str(np.round(np.mean(pixel_values),2))
                    contrast_data[contrast]['stddev']=str(np.round(np.std(pixel_values),2))
                    contrast_data[contrast]['median']=str(np.round(np.median(pixel_values),2))
                    contrast_data[contrast]['range']=str(np.round(np.percentile(pixel_values,25),2))+' - '+str(np.round(np.percentile(pixel_values,75),2))
                else:
                    add_to_log('WARNING apply_rois_to_mmdi3d_contrasts(): no valid pixels for '+contrast+', returning null output',logger)
            
            #Warning user when no image paths found
            else:
                add_to_log('WARNING apply_rois_to_mmdi3d_contrasts(): no slices have all required image paths for '+contrast+', returning null output',logger)
    
    #Returning contrast data
    return contrast_data

def measure_mmdi3d_contrasts_in_rois(alc2_digest:str,temp_dir:str='default',inversion_3d_dir:str='default',exclude_negative_pixels:bool=False,logger:str='None')->tuple:
    """
    measure_mmdi3d_contrasts_in_rois():
    Collects ROI and contrast slice data for an alc2_digest
    Uses slice data to apply ROIs to mmdi3d contrasts and obtain measurements
    See get_mmdi3d_slice_data() for default temp_dir and inversion_3d_dir
    If exclude_negative_pixels=True negative pixels for storage, loss, and attenuation measurements will be excluded
    Returns tuple of dict slice_data and dict contrast_data
    """
    slice_data=get_mmdi3d_slice_data(alc2_digest,temp_dir,inversion_3d_dir,logger)
    contrast_data=apply_rois_to_mmdi3d_contrasts(slice_data,exclude_negative_pixels,logger)
    return (slice_data,contrast_data)