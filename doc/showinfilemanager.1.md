---
title: SHOW IN FILE MANAGER
section: 1
header: General Commands Manual
footer: showinfilemanager
date: 2021-08-13
---
# NAME
showinfilemanager - open the file manager and select files in it

# SYNOPSIS
**showinfilemanager** [**-h**] [**--version**] [**--verbose**] [**--debug**] [**URIs ...**]

# DESCRIPTION
**showinfilemanager** opens the system file manager and optionally selects files in it. The point is not to *open* the 
files, but to *select* them in the file manager, thereby highlighting the files and allowing the user to quickly do
something with them. 

For file managers that do not support specifying files to select, this program will instruct them to display the
directory the file is found in. 

**URIs**
: URIs or paths of files or directories.

**-h**, **--help** 
: Display help message.

**--version** 
: Show program's version number and exit.

**-f**, **--file-manager** **FILE_MANAGER**
: File manager to run

**-s**, **--select-folder**
: Select folder instead of displaying its contents. By default, when a URI or path is a directory and
  not a file, the directory itself is shown in the file manager. This option changes the default and 
  selects the folder, displaying it in its parent directory.

**--verbose**
: Display command being run to stdout.

**--debug**
: Output debugging information to stdout.

# EXAMPLES
**showinfilemanager ~/myfile.txt**
: Open the system file manager and select *~/myfile.txt* in the user's home directory.

**showinfilemanager -f dolphin \*.txt**
: Open the dolphin file manager and select all the files with extension *txt* in the current directory.

**showinfilemanager D:\\Documents\\\*.docx**
: Open the system file manager and select all the Word documents in the Documents directory on the D: drive.

**showinfilemanager -s /Users/***
: Open the system file manager and select all the files and directories in the Users folder

**showinfilemanager file:///home/user/first%20file.txt file:///home/user/second%20file.txt**
: Open the system file manager and select 'first file.txt' and 'second file.txt' in the user's home directory.

**showinfilemanager /etc/hosts /home/user/.bashrc**
: Open the system file manager and select the hosts file in one file manager window, and the user's .bashrc file in 
another.


# AUTHORS
Damon Lynch  
damonlynch@gmail.com

# BUGS
Submit bug reports online at: <https://github.com/damonlynch/showinfilemanager/issues>

# SEE ALSO
Full documentation and sources at: <https://github.com/damonlynch/showinfilemanager>