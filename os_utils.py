"""
os_utils.py
Functions for OS support in Hepatogram Plus
"""
import os, re, glob, shutil, subprocess
from pathlib import Path, PureWindowsPath
if os.name=='nt':
    import win32com.client
    USE_SHELL=False
else:
    USE_SHELL=True

def dir_item_list(dir:str,item:str,include_dir:bool=False)->list:
    """
    dir_item_list():
    Returns a list of the folder or file names in a given dir
    If include_dir=True, will return as full paths
    """
    if item=='folder':
        item_list=next(os.walk(dir))[1]
    elif item=='file':
        item_list=next(os.walk(dir))[2]
    else:
        print("WARNING dir_item_list(): item "+str(item)+" not 'folder' or 'file', returning empty list")
        return []
    if include_dir:
        item_list=[os.path.join(dir,x) for x in item_list]
    return item_list

def dir_folder_list(dir:str,include_dir:bool=False)->list:
    """
    dir_folder_list():
    Calls dir_item_list() for folders
    """
    return dir_item_list(dir,'folder',include_dir)

def dir_file_list(dir:str,include_dir:bool=False)->list:
    """
    dir_file_list():
    Calls dir_item_list() for files
    """
    return dir_item_list(dir,'file',include_dir)

def os_clean_path(path:str)->str:
    """
    os_clean_path():
    Converts path to a clean format for the current OS
    Windows paths in Linux are converted to Linux format
    Ensures Linux paths start with single '/'
    """
    if (os.name!='nt') and ('\\' in path):
        path=Path(PureWindowsPath(path))
    path=os.path.normpath(path)
    if path.startswith('//'):
        path=path[1:]
    return path

def num_path_elems(path:str,clean_path_first:bool=True)->int:
    """
    num_path_elems():
    If clean_path_first=True, first calls os_clean_path() on path
    Returns the number of elements in path, excluding the root directory
    """
    if clean_path_first:
        path=os_clean_path(path)
    count=0
    while path!=os.path.dirname(path):
        count=count+1
        path=os.path.dirname(path)
    return count

def path_split(path:str,n_elem:int=1,clean_path_first:bool=True)->str:
    """
    path_split():
    If clean_path_first=True, first calls os_clean_path() on path
    Returns path and empty str for n_elem<1
    Returns tuple (head,tail) where tail is the n_elem last elements of path and head is the remainder
    """
    if clean_path_first:
        path=os_clean_path(path)
    if n_elem<1:
        return (path,'')
    head,tail=os.path.split(path)
    for i in range(1,n_elem):
        head,dpath=os.path.split(head)
        tail=os.path.join(dpath,tail)
    return(head,tail)

def find_existing_composite_path(path_1:str,path_2:str)->str:
    """
    find_existing_composite_path():
    Attempts to find an existing composite path from head components of path_1 and tail components of path_2
    WARNs and returns 'None' if none found
    """
    #Initializing
    path_1=os_clean_path(path_1)
    path_2=os_clean_path(path_2)

    #Searching for candidate composite path
    for j in range(1,num_path_elems(path_2)+1):
        head_2,tail_2=path_split(path_2,j)
        for i in range(1,num_path_elems(path_1)+1):
            head_1,tail_1=path_split(path_1,i)
            candidate_path=os.path.join(head_1,tail_2)
            if os.path.exists(candidate_path):
                return candidate_path
    
    #WARNING if no candidate found and returning 'None'
    print('WARNING find_existing_composite_path(): no existing composite path found for '+str(path_1)+' and '+str(path_2))
    return 'None'

def make_clean_dir(path, clean=True):
    if os.path.exists(path) and clean:
        shutil.rmtree(path)
    os.makedirs(path, exist_ok=True)
    return

def make_new_dirs(folders,clean_subdirs=True,max_nesting=1):
    if isinstance(folders,str): 
        folders = [folders]
    for folder in folders:
        # Also make parent folders n levels up. 
        make_parent_dirs(folder,max_nesting)
        if clean_subdirs and os.path.exists(folder): 
                delete_directory(folder)
        if not os.path.exists(folder): 
            os.mkdir(folder)

def make_parent_dirs(folder,max_nesting): 
    nesting = 0
    folder_level_not_exists = os.path.dirname(folder)
    folders_to_make = list()
    while not os.path.exists(folder_level_not_exists) and nesting <= max_nesting: 
        folders_to_make.append(folder_level_not_exists)
        folder_level_not_exists = os.path.dirname(folder_level_not_exists)
        nesting += 1
    for make_folder in folders_to_make[::-1]: 
        os.mkdir(make_folder)

def move_and_merge_dirs(source, destination):
    check_origin_target_same(source,destination)
    contents = glob.glob(os.path.join(source,'*'))
    for content in contents: 
        shutil.move(content,os.path.join(destination,os.path.basename(content)))
    delete_directory(source)

def resolve_symlink(link): 
    if os.name == 'nt':
        # According to documentation, os.path.realpath shoudl work on windows but it has no effect
        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortCut(link)
        path_digest = shortcut.Targetpath
    else:
        path_digest = os.path.realpath(link)
    return path_digest

def natural_sort(dir_list):
    # Function for sorting files/directories/other lists in natural order and not 1, 10, 100, 2, 20
    # Add feature - first first or directories first
    convert = lambda text: int(text) if text.isdigit() else text.lower()
    alphanum_key = lambda key: [convert(c) for c in re.split('([0-9]+)', key)]
    return sorted(dir_list, key=alphanum_key)

def delete(target): 
    if os.path.isdir(target):
        delete_directory(target)
    elif os.path.exists(target):
        os.remove(target)

def delete_directory(target_directory): 
    # This module uses OS calls to speed up removal of large numbers of files compared to shutil's rmtree
    if os.path.exists(target_directory): 
        if os.name == 'nt': 
            command = 'rmdir /s /q'
        else: 
            command = 'rm -rf'

        output = subprocess.check_output(command + ' ' + target_directory,shell=True)
        if output: 
            print('Cannot delete directory - check file lock: ' + target_directory)
    else: 
        print('Directory to be deleted does not exist: ' + target_directory)

def list_dir(directory,mask='*',target_type='',file_name_only=False): 
    contents = glob.glob(os.path.join(directory,mask))
    
    if not isinstance(directory,str) or not isinstance(target_type,str) or not isinstance(mask,str): 
        raise(TypeError('Directory, type, and mask need to be strings.'))

    if not os.path.isdir(directory): 
        raise(OSError('Input directory not valid.'))
        
    # Mask to only return files or folders
    if target_type == 'files': 
        contents = [name for name in contents if os.path.isfile(name)]
    elif target_type == 'folders' or target_type == 'dirs': 
        contents = [name for name in contents if os.path.isdir(name)]
    
    contents = [os.path.join(directory,name) for name in contents]
    if file_name_only: 
        contents = [os.path.basename(name) for name in contents]
    return natural_sort(contents)

def list_files(directory,mask='*',file_name_only=False): 
    files = list_dir(directory=directory,mask=mask,file_name_only=file_name_only,target_type='files')
    return files

def list_directories(directory,mask='*',file_name_only=False): 
    folders = list_dir(directory=directory,mask=mask,file_name_only=file_name_only,target_type='folders')
    return folders

def copy_dir(source,destination): 
    check_origin_target_same(source,destination)
    make_new_dirs(destination) # Attempt to make target directory (will recreate limited number of levels)
    if not source.endswith('*'): 
        contents = [source]
    else: 
        contents = list_dir(source[:-1]) 
    for content in contents: 
        copy(content,destination)

def copy(source,destination): 
    check_origin_target_same(source,destination)
    if not os.path.exists(source): 
        raise(OSError('Source to copy does not exist: ' + source))
    if not os.path.exists(destination) or not os.path.isdir(destination): 
        raise(OSError('Copy target directory does not exist: ' + destination))
    if os.path.isfile(source): 
        shutil.copy(source,os.path.join(destination,os.path.basename(source)))
    elif os.path.isdir(source): 
        shutil.copytree(source,os.path.join(destination,os.path.basename(source)))

def parent_dir(path,level,dir_only=False): 
    path = str(Path(path).parents[level-1])
    if dir_only: 
        path = os.path.basename(path)
    return path

def parent_dir_name(path,level): 
    return parent_dir(path,level,dir_only=True)

def extract_file_from_artifact(exec,result_dir,file): 
    target_file = os.path.join(result_dir, file)
    if os.name == 'nt': 
        shutil.copyfile(os.path.join(exec,'mreplus_config',file),target_file)
    else: 
        os.system('docker exec ' + exec + ' /bin/bash -c "' + 'cat mreplus_config/' + file + ' > ' \
            + target_file + '"')
    return target_file

def check_origin_target_same(origin,target): 
    if origin == target: 
        # This may be caused by pathjoin - if arguments after first are paths, original path will be overridden. 
        raise(ValueError('Source is the same as the destination.'))

def run_cmd_with_logging(cmd,cwd=None,logger='None'):
    """
    run_cmd_with_logging():
    Runs str cmd with optional str cwd
    Captures command output in logger object
    Returns exit code of command
    """
    #Running command
    process=subprocess.Popen(cmd,
                             cwd=cwd,
                             stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT,
                             shell=USE_SHELL)

    #Capturing command output
    if logger!='None':
        for line in process.stdout:
            logger.info(line.decode('utf-8').strip())
    else:
        for line in process.stdout:
            print(line.decode('utf-8').strip())
    
    #Returning exit code
    exit_code=process.wait()
    return exit_code