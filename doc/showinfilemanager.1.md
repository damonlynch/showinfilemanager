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
: URIs or paths of files or directories

**-h**, **--help** 
: display help message

**--version** 
:  show program's version number and exit

**--verbose**
: display command being run to stdout

**--debug**
: output debugging information to stdout

# EXAMPLES
**showinfilemanager ~/myfile.txt**
: Open the system file manager and select *~/myfile.txt* in the user's home directory

**showinfilemanager file:///home/user/first%20file.txt file:///home/user/second%20file.txt**
: Open the system file manager and select 'first file.txt' and 'second file.txt' in the user's home directory

**showinfilemanager /etc/hosts /home/user/.bashrc**
: Open the system file manager and select the hosts file in one file manager window, and the user's .bashrc file in 
another


# AUTHORS
Damon Lynch  
damonlynch@gmail.com

# BUGS
Submit bug reports online at: <https://github.com/damonlynch/showinfilemanager/issues>

# SEE ALSO
Full documentation and sources at: <https://github.com/damonlynch/showinfilemanager>