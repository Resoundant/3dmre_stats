"""
dicom_and_file_utils.py
Functions for supporting DICOMs and other files in Hepatogram Plus
"""
import os, sys, shutil, glob, re, json, datetime, numpy, pydicom
from hashlib import sha256
from os_utils import dir_file_list, os_clean_path, find_existing_composite_path, list_dir, list_files
if os.name=='nt':
    import win32com.client

def rename_files(path_received,path_target=''):
    if not path_target: 
        path_target = path_received
    files = list_dir(path_received, mask='*.dcm')
    for file in files:
        try:
            ds = pydicom.dcmread(file, stop_before_pixels=True)
            series_number = str(ds.SeriesNumber)
            series_description = re.sub('[^A-Za-z0-9 ]', '', ds.SeriesDescription).replace(' ','_')
            subdir_out = os.path.join(path_target,series_number + '_' + series_description)
            file_name = str(ds.InstanceNumber).zfill(4) + '.dcm'
        except Exception as e:
            print(str(e))
            os.remove(file)
            continue
        
        if not os.path.isdir(subdir_out):
            os.mkdir(subdir_out)
        
        file_out = os.path.join(subdir_out, file_name)
        shutil.move(file, file_out)

def rename_subdirs(path_received):
    if not os.path.isdir(path_received):
        raise Exception('The specified path does not exist: ' + path_received + '. Check that it is mounted.')
    else:
        subdirs = list_dir(path_received,target_type='folders')
        for subdir in subdirs:
            path_subdir = os.path.join(path_received, subdir)
            subdir_out = rename_files(path_subdir,path_received)
            if subdir_out:
                os.rename(os.path.join(path_received,subdir),os.path.join(path_received,subdir_out))
        rename_files(path_received)

def extract_hidden_tags(top_dir,key_tags):
    subdirs = [name for name in glob.glob(os.path.join(top_dir,'*')) if os.path.isdir(name)]
    for subdir in subdirs:
        has_relevant_hidden_tags = False
        files = glob.glob(os.path.join(subdir,'*.dcm'))

        for file_number, file in enumerate(files):
            try:
                ds = pydicom.read_file(file)
                key_tags_missing = [name for name in key_tags if name not in ds.dir()]
                if key_tags_missing:
                    if file_number == 0:
                        ds, has_relevant_hidden_tags = search_and_extract(ds, key_tags)
                    elif file_number > 1 and has_relevant_hidden_tags:
                        ds, _ = search_and_extract(ds, key_tags)

                    if has_relevant_hidden_tags:
                        ds.save_as(file)
            except Exception as e:
                print(e)

def search_and_extract(ds, key_tags):
    has_relevant_hidden_tags = False
    # subfields = [name for name in ds.dir()]
    for subfield in ds.keys():
        if ds[subfield].VR == 'SQ':
            # print(subfield)
            for item in ds[subfield].value:
                # Recurse this function to flatten expanding any sub-sub fields
                item, _ = search_and_extract(item, key_tags)

                available_tags = [name for name in item.dir() if name in key_tags]
                if available_tags:
                    has_relevant_hidden_tags = True
                    for available_tag in available_tags:
                        ds[available_tag] = ds[subfield][0][available_tag]
                        # print(available_tag)

            del ds[subfield]
    return ds, has_relevant_hidden_tags

def fill_empty_tags(input):
    dt = datetime.datetime.now()
    myDatemeta = dt.strftime("%Y%m%d")  # YYYYMMDD
    myDateid = dt.strftime("%Y%m%d_%X").replace(":", "-")  # YYYYMMDD_hhhh-mm-ss
    for dirName, subdirList, fileList in os.walk(input):
        added_attribute = {'PatientName': False, 'PatientID': False, 'StudyID': False, 'ContentDate': False}
        files = [name for name in fileList if '.dcm' in name]
        for filename in files:
            try:
                saveDcm = False
                ds = pydicom.read_file(os.path.join(dirName, filename))
                # fill in empty, required fieldsfields
                attribute = 'PatientName'
                if (attribute not in ds) or (not ds.PatientName):
                    ds.PatientName = myDateid
                    saveDcm = True
                    added_attribute[attribute] = True
                attribute = 'PatientID'
                if (attribute not in ds) or (not ds.PatientID) or (ds.PatientID.isspace()):
                    ds.PatientID = ds.PatientName.family_name
                    saveDcm = True
                    added_attribute[attribute] = True
                attribute = 'StudyID'
                if (attribute not in ds) or (not ds.StudyID):
                    ds.StudyID = ds.PatientID
                    saveDcm = True
                    added_attribute[attribute] = True
                attribute = 'ContentDate'
                if (attribute not in ds) or (not ds.ContentDate):
                    ds.ContentDate = myDatemeta
                    saveDcm = True
                    added_attribute[attribute] = True

                # Delete embedded sequences
                if ['0088', '00200'] in ds:
                    del ds['0088', '00200']

                if saveDcm:
                    ds.save_as(os.path.join(dirName, filename))
            except Exception as e:
                print("Error in file " + (os.path.join(dirName, filename)))

        if any(added_attribute.values()):
            attributes_added = ''
            for key in added_attribute:
                if added_attribute[key]:
                    attributes_added += key + ' '
            print('Added ' + attribute + ' to ' + dirName)

def preprocess_dicom_tags(input,flags): 
    if flags.fill_empty_tags:
        fill_empty_tags(input)
    if flags.extract_dicom_tags:
        extract_hidden_tags(input,flags.extract_dicom_tags)
    if flags.remove_fields_missing_VR: 
        remove_fields_with_missing_vr(input) 
    if flags.remove_all_seq: 
        remove_all_seq_fields(input) 

def remove_all_seq_fields(input): 
    for dirName, subdirList, fileList in os.walk(input):
        files = [name for name in fileList if '.dcm' in name]
        for filename in files:
            try:
                file_path = os.path.join(dirName, filename)
                ds = pydicom.read_file(file_path)
                for key in list(ds.keys()): 
                    if ds[key].VR == 'SQ': 
                        del ds[key]
                ds.save_as(file_path)
            except Exception as e:        
                    print("Error removing SEQ tags" + (os.path.join(dirName, filename)))

def remove_fields_with_missing_vr(input):
    for dirName, subdirList, fileList in os.walk(input):
        files = [name for name in fileList if '.dcm' in name]
        for filename in files:
            try:
                file_path = os.path.join(dirName, filename)
                ds = pydicom.read_file(file_path)
                for key in list(ds.keys()): 
                    if not ds[key].VR: 
                        del ds[key]
                ds.save_as(file_path)
            except Exception as e:        
                print("Error removing Tags with missing VR" + (os.path.join(dirName, filename)))

def insert_patient_name(exam): 
    name_to_insert = os.path.basename(exam)
    insert_patient_name_files(exam,name_to_insert)

    folders = list_dir(exam,target_type='folders')
    for folder in folders: 
        insert_patient_name_files(folder,name_to_insert)

def insert_patient_name_files(folder,name_to_insert): 
    files = list_dir(folder,target_type='files')
    for file in files: 
        try: 
            ds = pydicom.read_file(file)
            ds['PatientName'].value = name_to_insert
            ds['PatientID'].value = name_to_insert
            ds.save_as(file)
        except: 
            print('Not a valid DICOM file: ' + file)

def read_images(paths): 
    if type(paths) == dict: 
        paths = paths.values()
    i = 0
    for slice in paths: 
        ds = pydicom.read_file(slice)
        if i==0: 
            images = numpy.zeros((ds.pixel_array.shape[0],ds.pixel_array.shape[1],len(paths)))
            images[:,:,i] = numpy.array(ds.pixel_array,dtype=float)
        else: 
            images[:,:,i] = numpy.array(ds.pixel_array,dtype=float)
        i += 1
    return images

def remove_extra_matlab_images(subdir): 
    """ Remove in-house Matlab images which are sometimes merged into scanner data and screw up sorting/processing. """
    files = list_files(subdir)
    matlab_files_removed = False
    for file in files: 
        try: 
            ds = pydicom.read_file(file,stop_before_pixels=True)
            if ['0002','0013'] in ds.file_meta and 'MATLAB' in ds.file_meta['0002','0013'].value.upper(): # Implementation Verion Name 
                os.unlink(file)
                matlab_files_removed = True
        except: 
            pass
    if matlab_files_removed: 
        print('Removed Matlab files in: ' + subdir)
    return

def remove_cloned_slices(input): 
    if os.path.isdir(input): 
        files = list_files(input)
    else: 
        files = input
    locations_present = []
    files_remove = []
    for file in files: 
        ds = pydicom.read_file(file,stop_before_pixels=True)
        if ds.SliceLocation not in locations_present: 
            locations_present.append(ds.SliceLocation)
        else: 
            files_remove.append(file)
            # os.unlink(file)
    return

def find_3D_like(input): 
    if os.path.isdir(input): 
        files = list_files(input)
    else: 
        files = input
    ds = pydicom.read_file(files[0])
    if ('SeriesDescription' not in ds):
        return
    
    print(ds.SeriesDescription)
    if 'GE' in ds.Manufacturer.upper():
        manufacturer = 'GE'
    # elif 'SIEMENS' in ds.Manufacturer.upper():
    #     manufacturer = 'Siemens'
    # elif 'PHILIPS' in ds.Manufacturer.upper():
    #     manufacturer = 'Philips'

    valid_like = manufacturer == 'GE' and 'MRE' in ds.SeriesDescription and ('EPI' in ds.SeriesDescription or '3D' in ds.SeriesDescription) \
        and ('SequenceName' not in ds or '3d-mmdi' not in ds.SequenceName) 
    return valid_like

def pixeldata_hash(file_path):
    """
    pixeldata_hash():
    Returns the sha256 hash of the PixelData stored in DICOM at file_path
    Returns 'no_pixeldata' if DICOM file can't be opened or PixelData absent
    """
    try:
        dcm=pydicom.read_file(file_path)
    except pydicom.errors.InvalidDicomError:
        print("WARNING pixeldata_hash(): unable to read DICOM from "+file_path)
        hash='no_pixeldata'
    else:
        if dcm.get('PixelData')==None:
            print('WARNING pixeldata_hash(): no PixelData in '+file_path)
            hash='no_pixeldata'
        else: 
            hash=sha256(dcm.PixelData).hexdigest()
    return hash

def get_series_uids(top_dir):
    """
    get_series_uids():
    Returns list series_uids of the unique SeriesInstanceUIDs found in DICOMs in top_dir
    """
    #Searching top_dir for unique SeriesInstanceUID in DICOMs
    series_uids=[]
    for dir, subdirs, files in os.walk(top_dir):
        for file in files:
            if file.endswith('.dcm'):
                #Opening DICOM
                file_path=os.path.join(dir,file)
                dcm=pydicom.dcmread(file_path,stop_before_pixels=True)

                #Extracting SeriesInstanceUID
                series_uid=dcm.get('SeriesInstanceUID','')
                if (series_uid not in series_uids) and (series_uid!=''):
                    series_uids.append(series_uid)
    
    #Returning results
    return series_uids

def get_return_metadata(top_dir):
    """
    get_return_metadata():
    Returns dict metadata containing first found job ID and AE title in DICOMs of top_dir
    Limits number of DICOMs checked to int loops_max
    """
    #Initializing
    job_id_default='no_job_id'
    job_id=job_id_default
    return_aet_default='HPRT_DEFAULT'
    return_aet=return_aet_default
    loops=0
    loops_max=5

    #Searching top_dir for job ID and AE title
    for dir, subdirs, files in os.walk(top_dir):
        #Skip hepplus temp and output directories
        if dir.endswith('temp') or dir.endswith('output'):
            continue
        for file in files:
            if 'DICOMDIR' in file:
                continue
            try:
                file_path=os.path.join(dir,file)
                dcm=pydicom.dcmread(file_path,stop_before_pixels=True)
            except:
                continue
            
            #Extracting job ID and AE title
            if (job_id==job_id_default) and (dcm.get(0x00400006)!=None):
                job_id=dcm.get(0x00400006).value
            if (return_aet==return_aet_default) and (dcm.get(0x00400001)!=None):
                return_aet=dcm.get(0x00400001).value
            
            #Break loop if both tags found or max loops exceeded
            loops+=1
            if ((job_id!=job_id_default) and (return_aet!=return_aet_default)) or (loops>loops_max):
                break 

        #Break loop if both tags found or max loops exceeded
        if ((job_id!=job_id_default) and (return_aet!=return_aet_default)) or (loops>loops_max):
            break
    
    #Return results
    metadata={'job_id':job_id,'return_aet':return_aet}
    return metadata

def get_alc_digest_series(digest_path:str):
    """
    get_alc_digest_series():
    Attempts to get the MRE and FW series information at the end of a .alc file name
    Assumes the first 4 components of the file name separated by '_' precede the series information
    """
    file=os.path.basename(os_clean_path(digest_path))
    if '.alc' not in file:
        print("WARNING get_alc_digest_series(): "+digest_path+" file name does not contain '.alc', returning empty str")
        return ''
    series=('_'.join(file.split('_')[4:])).split('.alc')[0]
    return series

def parse_digest(digest_path:str):
    """
    parse_digest():
    Parses a digest file into dict content of key-value pairs and set comments of comment strings
    Comments following values are discarded
    """
    #Initializing
    content=dict()
    comments=set()
    
    #Opening digest
    with open(digest_path) as f_obj:
        lines=f_obj.read().splitlines()
    
    #Removing empty lines
    lines=list(filter(None,lines))
    lines=list(filter(lambda x:(x!=' '),lines))

    #Scraping content
    for line in lines:
        mystr=line.split('%',maxsplit=1)
        if len(mystr)>1:
            comments.add(mystr[1].strip)
        mystr2=mystr[0].split('=',maxsplit=1)
        if len(mystr2)>1:
            key=mystr2[0].strip()
            val=mystr2[1].strip()
            content[key]=val
    
    #Returning output
    return (content,comments)

def save_alc_digest_as_json(digest_path:str):
    """
    save_alc_digest_as_json():
    Loads an alc digest with parse_digest() and saves out content to a json file
    """
    digest_head,digest_ext=os.path.splitext(digest_path)
    if not digest_ext.lower().startswith('.alc'):
        print('WARNING save_alc_digest_as_json(): not an alc digest '+str(digest_path)+', no json file saved')
        return
    content,comments=parse_digest(digest_path)
    json_path=digest_head+'_'+digest_ext[1:]+'.json'
    with open(json_path,'w') as json_obj:
        json.dump(content,json_obj)
    return

def make_digest_links(temp_dir,done_cases_dir):
    """
    make_digest_links():
    Creates links in done_cases_dir for each alc2 digest in temp_dir
    """
    #Initializing
    os.makedirs(done_cases_dir,exist_ok=True)
    shell=win32com.client.Dispatch('WScript.Shell')

    #Creating links
    for file in dir_file_list(temp_dir):
        if file.lower().endswith('.alc2'):
            file_path=os.path.join(temp_dir,file)
            link_path=os.path.join(done_cases_dir,file+'.lnk')
            link=shell.CreateShortCut(link_path)
            link.TargetPath=file_path
            link.save()
    return

def get_dcm_tag_from_dir(dir,tag,default_value='',first_hit=True):
    """
    get_dcm_tag_from_dir():
    Searches dir for DICOM files and looks up tag in each
    If tag exists in the file, stores its value in dict values, else stores default_value
    If first_hit==True, will return the first non default_value found, or default_value if none found
    If first_hit==False, returns values
    """
    values=dict()
    for file in dir_file_list(dir):
        if file.lower().endswith('.dcm'):
            dcm_path=os.path.join(dir,file)
            try:
                dcm=pydicom.read_file(dcm_path)
            except:
                continue
            else:
                values[file]=dcm.get(tag,default_value)
                if (values[file]!=default_value) and (first_hit==True):
                    return values[file]
    if first_hit==True:
        return default_value
    else:
        return values

def get_dcm_pixel_data(dcm_paths:list):
    """
    get_dcm_pixel_data():
    Creates numpy.array image of zeros with same dimensions as first DICOM image in dcm_paths and length of dcm_paths
    Adds pixel data to image from each DICOM in dcm_paths with same dimensions, skipping if dimensions are different
    Returns image
    """
    #Initializing
    dcm=pydicom.read_file(dcm_paths[0])
    N_rows=dcm.pixel_array.shape[0]
    N_cols=dcm.pixel_array.shape[1]
    N_dcms=len(dcm_paths)
    image=numpy.zeros((N_rows,N_cols,N_dcms))

    #Getting pixel data
    for i in range(N_dcms):
        dcm=pydicom.read_file(dcm_paths[i])
        if (dcm.pixel_array.shape[0]!=N_rows) or (dcm.pixel_array.shape[1]!=N_cols):
            print('WARNING get_dcm_pixel_data(): DICOM image at '+dcm_paths[i]+' of different dimension than baseline at '+dcm_paths[0]+', skipping')
        else:
            image[:,:,i]=numpy.array(dcm.pixel_array,dtype=float)
    return image

def get_dcm_paths_from_digest(digest_path:str,key_start:str):
    """
    get_dcm_paths_from_digest():
    Scrapes digest at digest_path for keys starting with key_start with values ending in '.dcm'
    Constructs dict dcm_paths_dict with valid keys and values the currently existing paths of the associated DICOM images and returns
    """
    #Initializing
    dcm_paths_dict=dict()
    content,comments=parse_digest(digest_path)
    
    #Scraping digest for DICOM paths
    for key in content.keys():
        if key.startswith(key_start) and content[key].lower().endswith('.dcm'):
            dcm_path=content[key]
            composite_path=find_existing_composite_path(digest_path,dcm_path)
            if composite_path!='None':
                dcm_paths_dict[key]=composite_path
            else:
                sys.exit('ERROR get_dcm_paths_from_digest(): unable to find existing location for DICOM file '+dcm_path+' listed in digest '+digest_path)
    return dcm_paths_dict

def get_roi_and_elastogram_images_from_digest(digest_path:str):
    """
    get_roi_and_elastogram_images_from_digest():
    Gets ROI and elastogram DICOM paths from digest at digest_path
    For each ROI image path, attempts to pair with an elastogram image path
    All matched pairs of image paths are used to load ROI and elastogram images and returned
    """
    #Getting ROI and elastogram DICOM paths
    roi_paths_dict=get_dcm_paths_from_digest(digest_path=digest_path,key_start='mre.roi.')
    elastogram_paths_dict=get_dcm_paths_from_digest(digest_path=digest_path,key_start='mre.stiff.')

    #Getting paired ROI and elastogram paths
    roi_paths,elastogram_paths=[],[]
    for roi_key in roi_paths_dict.keys():
        key_ending=roi_key.split('mre.roi.')[-1]
        elastogram_key='mre.stiff.'+key_ending
        if elastogram_key in elastogram_paths_dict.keys():
            roi_paths.append(roi_paths_dict[roi_key])
            elastogram_paths.append(elastogram_paths_dict[elastogram_key])
    if len(roi_paths)<len(roi_paths_dict):
        print('WARNING get_roi_and_elastogram_images_from_digest(): not all ROI DICOM paths paired with an elastogram DICOM path')
    
    #Getting ROI and elastogram images and returning
    roi_image=get_dcm_pixel_data(roi_paths)
    roi_image=(roi_image!=0).astype(int)
    elastogram_image=get_dcm_pixel_data(elastogram_paths)
    return (roi_image,elastogram_image)

def get_roi_and_ffrac_images_from_digest(digest_path:str):
    """
    get_roi_and_ffrac_images_from_digest():
    Gets ROI and fat fraction DICOM paths from digest at digest_path
    For each ROI image path, attempts to pair with a fat fraction image path
    All matched pairs of image paths are used to load ROI and fat fraction images and returned
    """
    #Getting ROI and fat fraction DICOM paths
    roi_paths_dict=get_dcm_paths_from_digest(digest_path=digest_path,key_start='fw.roi.')
    ffrac_paths_dict=get_dcm_paths_from_digest(digest_path=digest_path,key_start='fw.ffrac.')

    #Getting paired ROI and fat fraction paths
    roi_paths,ffrac_paths=[],[]
    for roi_key in roi_paths_dict.keys():
        key_ending=roi_key.split('fw.roi.')[-1]
        ffrac_key='fw.ffrac.'+key_ending
        if ffrac_key in ffrac_paths_dict.keys():
            roi_paths.append(roi_paths_dict[roi_key])
            ffrac_paths.append(ffrac_paths_dict[ffrac_key])
    if len(roi_paths)<len(roi_paths_dict):
        print('WARNING get_roi_and_ffrac_images_from_digest(): not all ROI DICOM paths paired with a fat fraction DICOM path')
    
    #Getting ROI and fat fraction images and returning
    roi_image=get_dcm_pixel_data(roi_paths)
    roi_image=(roi_image!=0).astype(int)
    ffrac_image=get_dcm_pixel_data(ffrac_paths)

    #Rescaling fat fraction values
    for i in range(len(ffrac_paths)):
        dcm=pydicom.read_file(ffrac_paths[i],stop_before_pixels=True)
        slope=dcm.get('RescaleSlope')
        intercept=dcm.get('RescaleIntercept')
        if slope and intercept:
            ffrac_image[:,:,i]=float(slope)*ffrac_image[:,:,i]+float(intercept)
        elif (not slope) and intercept:
            print('WARNING get_roi_and_ffrac_images_from_digest(): no rescaling applied, found intercept but no slope for '+ffrac_paths[i])
        elif (not intercept) and slope:
            print('WARNING get_roi_and_ffrac_images_from_digest(): no rescaling applied, found slope but no intercept for '+ffrac_paths[i])
        elif dcm.get('ImageComments')=='Gray value 1 equals 0.1%':
            ffrac_image[:,:,i]=0.1*ffrac_image[:,:,i]
        elif (numpy.quantile(ffrac_image[:,:,i],q=0.10)<0) or (100<numpy.quantile(ffrac_image[:,:,i],q=0.90)):
            print('WARNING get_roi_and_ffrac_images_from_digest(): no rescaling applied, but a significant amount of pixel values are out of range 0-100 for '+ffrac_paths[i])
    
    #Upscaling
    if (roi_image.shape[0]>ffrac_image.shape[0]) and (roi_image.shape[0]%ffrac_image.shape[0]==0) and ((roi_image.shape[0]/ffrac_image.shape[0])==(roi_image.shape[1]/ffrac_image.shape[1])):
        zoom=int(roi_image.shape[0]/ffrac_image.shape[0])
        ffrac_image=numpy.repeat(numpy.repeat(ffrac_image,zoom,axis=0),zoom,axis=1)

    #Returning results
    return (roi_image,ffrac_image)

def get_original_alc2_digest(digest_path:str):
    """
    get_original_alc2_digest():
    For a given alc2 digest_path, attempts to find its original version in the same directory
    First looks for an alc2_01 version of the digest, then the earliest alc2_timestamped version, and returns result
    If no older file found, returns original digest_path
    """
    #Checking for alc2 file
    if not digest_path.lower().endswith('.alc2'):
        print("WARNING get_original_alc2_digest(): "+str(digest_path)+" is not an alc2 digest, returning 'ERROR'")
        return 'ERROR'
    
    #Initializing
    digest_path_original=digest_path
    digest_dir=os.path.dirname(digest_path)
    digest_file=os.path.basename(digest_path)
    files=[x for x in os.listdir(digest_dir) if x.startswith(digest_file)]
    
    #Searching for alc2_01 file
    if (digest_file+'_01') in files:
        digest_path_original=os.path.join(digest_dir,digest_file+'_01')
    
    #Searching for earliest alc2_timestamped file
    else:
        files_timestamped=[x for x in files if len(x)==len(digest_file)+16]
        if len(files_timestamped)>0:
            files_timestamped.sort()
            digest_path_original=os.path.join(digest_dir,files_timestamped[0])
    
    #Returning result
    return digest_path_original