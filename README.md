# SpaceEngineers-WGS-Recovery
An interactive Python utility to extract Microsoft Store Space Engineers cloud-synced saves, known as "WGS files" from Xbox or PC that were lost due to loading corrupted or invalid backups.
If you've ever loaded a backup of a save that resulted in your save being seemingly deleted or de-listed from the "Load Game" menu, this is for you.
(The backup was likely corrupted because your cloud storage was full when it tried to save.)
This utility does not write anything to WGS throughout the process, and only creates the recovered world to the prompted location.

You can also use this utility to perform local backups of cloud-synced saves.
In the future, I would like to add better backup functionality/QOL and blueprint detection.

Obviously, this only works on Windows.

## What Does It Do?
This utility attempts to scan your WGS (Microsoft cloud-sync) folders on your PC, assuming you have Space Engineers installed via Microsoft Store.
If you do not have Space Engineers installed, you're safe to install it and let it sync.
Basic save file verification is included that will attempt to determine if all important files are present.

## What Do I Do If I Just Lost My Save?
If you lost the save on Xbox:
 - Stop playing on Xbox, then on PC, launch (or install, then launch) Space Engineers. Give it time to sync your games once launched. Check your game settings and ensure you have cloud-syncing enabled. If not, you'll have to launch it. Continue to the usage steps.
 - If your computer can barely even run Space Engineers, don't worry. You will barely even need to load a world to re-sync it.

If you lost the save on PC:
 - Close Space Engineers, then continue to the usage steps.

## Usage Steps
First, if you have not already installed [Python](https://www.python.org/downloads/), do so now.

1. Download sewgsrecoverertool.py
2. Open the command line in the directory you downloaded the file to. Do this by right-clicking in the directory without a file selected and select "Open In Terminal."
   - For example, if you downloaded the file to Downloads:<img width="781" height="412" alt="Terminal right-click demostration" src="https://github.com/user-attachments/assets/0e4653e7-7b51-4b7e-a3aa-1ad7841cdf12" />
3. In Terminal, type "python sewgsrecoverertool.py"
4. The utility should now be started, and you are prompted to add a custom package location for backups or leave it blank for the default Space Engineers cloud storage location.
   - If a custom location was entered that does not meet the expected package configuration, you will be prompted to blindly search until the utility can find a folder that does.
6. The next steps are self-explanatory. The utility will list the worlds and allow you to inspect them for their thumbnail and/or provide a location to recover the world to (defaults to the SE save location).
   - Save inspection menu:<img width="1158" height="717" alt="627565367-7199980a-dda1-47b5-89dd-02d06d092aaa" src="https://github.com/user-attachments/assets/d6466550-c615-446b-b92d-8b8e9fde1b29" />
7. After the recovery is complete, you will be prompted as to what do do with a "manifest.json." This is a .json file that shows the correlation between the true file names and blob hex GUIDs. You can safely delete it if you do not want that information.
