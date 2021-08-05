# Show in File Manager

Platform independent way for a Python script to open the system file manager and optionally select files to highlight
in it. The point is not to open the file, but to display it in the operating system's file manager, preferably selected.

Plenty of programs provide this function. Phrases programs use vary depending on the context. 
Windows programs use terms like "Show in Windows Explorer", "Show in Explorer", and "Reveal in Explorer". 
Cross-platform programs can prefer terms like "Open Containing Folder" or "Open in File Browser".
On a downloading program, a term can be "Open destination folder".

![Show in Windows Explorer](.github/photomechanic-win.png)
![Open containing folder](.github/documentviewer-gnome.png)

The command results in the file manager opening, typically with the files selected:
![Gnome Files](.github/files-gnome.png)

## Rationale

There is no standard with which to open an operating system's file manager at a requested path,
and highlight files to display in it. 

On desktop Linux the problem is especially acute, as Linux provides a plethora of file managers, with no 
standard for specifying which files to highlight on a supplied path. Moreover, the system default file manager
as reported by `xdg-mime query default inode/directory` can be incorrectly set to nonsensical values,
such as an AppImage the user has installed.

## Status

As of today, the code needs to be written. The purpose of this initial release is to discuss preferred implementations. 


## License

[MIT](https://choosealicense.com/licenses/mit/)

  
## Authors

- [@damonlynch](https://github.com/damonlynch)



