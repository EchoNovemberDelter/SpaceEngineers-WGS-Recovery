# SpaceEngineers-WGS-Recovery
An interactive Python utility to extract Microsoft Store Space Engineers cloud-synced saves, known as "WGS files" from Xbox or PC that were lost due to loading corrupted or invalid backups.
If you've ever loaded a backup of a save that resulted in your save being seemingly deleted or de-listed from the "Load Game" menu, this is for you.
(The backup was likely corrupted because your cloud storage was full when it tried to save.)

<ins>This utility does not write anything to WGS throughout the process, and only creates the recovered world to the prompted location.<ins>

You can also use this utility to perform local backups of cloud-synced saves.
In the future, I plan to add better backup functionality/QOL and blueprint detection.

Obviously, this only works on Windows.

## What Does It Do?
- This utility attempts to scan your WGS (Microsoft cloud-sync) folders on your PC, assuming you have Space Engineers installed via Microsoft Store.
- If you do not have Space Engineers installed, you're safe to install it and let it sync [unless you explicitly deleted the save](#Deletion).
- Basic save file verification is included that will attempt to determine if all important files are present.

## What Do I Do If I Just Lost My Save?
If you lost the save on Xbox:
 - Stop playing on Xbox, then on PC, launch (or install, then launch) Space Engineers. Give it time to sync your games once launched. Check your game settings and ensure you have cloud-syncing enabled. If not, you'll have to relaunch it. Continue to the [usage steps](#usage-steps).
 - If your computer can barely even run Space Engineers, don't worry. You will barely even need to load a world to re-sync it. Drop all of your graphics and display settings as low as possible if necessary.

If you lost the save on PC:
 - Close Space Engineers, then continue to the [usage steps](#usage-steps).

## Usage Steps
First, if you have not already installed [Python](https://www.python.org/downloads/), do so now.

1. Download sewgsrecoverertool.py
2. Open the command line in the directory you downloaded the file to. Do this by right-clicking in the directory without a file selected and select "Open In Terminal."
   - For example, if you downloaded the file to Downloads:<img width="781" height="412" alt="Terminal right-click demonstration" src="https://github.com/user-attachments/assets/0e4653e7-7b51-4b7e-a3aa-1ad7841cdf12" />
3. In Terminal, type "python sewgsrecoverertool.py"
4. The utility should now be started, and you are prompted to add a custom package location for backups or leave it blank for the default Space Engineers cloud storage location.
   - If a custom location was entered that does not meet the expected package configuration, you will be prompted to blindly search until the utility can find a folder that contains at least one WGS save, even if it's not from Space Engineers. Attempting to read a non-SE package will end in error.
6. The next steps are self-explanatory. The utility will list the worlds and allow you to inspect them for their thumbnail image and/or provide a location to recover the world to (defaults to the SE save location).
   - Save inspection menu:<img width="1158" height="717" alt="The world listing menu" src="https://github.com/user-attachments/assets/d6466550-c615-446b-b92d-8b8e9fde1b29" />
   - You have the option to exit the tool before a recovery path is inputted. Once you've provided a path and pressed enter, the folder will be created and populated with world files.
   - The recovered save folder will open when complete.<img width="668" height="573" alt="FIle explorer of a recovered world folder" src="https://github.com/user-attachments/assets/8d190c1d-8ce2-423d-9d4a-b09e952eac0e" />
8. After the recovery is complete, you will be prompted as to what to do with a "manifest.json." This is a .json file that shows the correlation between the true file names and blob hex GUIDs. You can safely delete it if you do not want that information.

## Recovery Disclosure
The recovery process has only ever been confirmed to work in the specific scenario of a de-listed world because of a bad loaded backup. I have now recovered several words from up to a few years back lost in the same way with this utility, though it is still best practice to close SE immediately (or install and launch without loading any worlds) to prevent any possible overwriting or WGS decluttering.

<a name="Deletion"></a>
Theoretically, you could also recover deleted saves on Xbox by recovering the world from WGS on PC, without launching PC SE, to prevent re-syncing. Deleted worlds are truly removed from the cloud instead of being just de-indexed, so there's more risk. No promises.

## Save Reading And Recovery Process
> This is explaining how the code searches and recovers. You don't need to read this to use the utility unless you're interested.

The way Microsoft handles cloud-syncing of the data of supported games and apps is through the packages/WGS hidden folder, located in `%LocalAppData%\Packages\`. In that folder, there are many packages labelled under the name of the publisher of the app (In this case, "KeenSoftwareHouse"). It's likely that the desired folder name will not appear until you perform a search, due to being unindexed. There may be many KSH packages, but only one will have contents >1KB. In this folder you can follow through `SystemAppData\wgs\[Long hex ID]\`. Here is where your files are stored, albeit not in a human-readable manner. This is also where this utility does things differently than other WGS reading tools.

In this folder, along with all of the hex-named folders, you will see a "container.index" file. This is the index where the game will read to see what files are present in the cloud. Other WGS reading tools will simply decode this index to tell you what is present. However, in Space Engineers, loading corrupted/invalid backups of a save will just remove the index of that save without actually deleting the world from the cloud. Therefore, those other tools won't find it by reading the index. This utility will instead scan for and use the "container.#" file present in every one of those subfolders. The "container.#" file is the local index for that folder that contains the mapping that correlates the hex GUIDs with the actual name for that file. By decoding the container (using a method written in Python by other, smarter people and certainly documented better somewhere else) for each file and determining what is present, combined with the session name in the deobfuscated "Sandbox_config.sbc" XML file to determine the save name, this utility can create it's own index of the saves in the WGS system without relying on the master "container.index." It groups the saves with their respective files instead of just listing out every single file like alternative tools.

All these SE-specific solutions is why, even though it technically is a WGS decoder, it will only ever work for SE.

Some other games/apps may write their files to the cloud in slightly different ways (e.g. with different header and footer byte lengths) that other tools are better suited to handle.

##

> The entire script was made with VSCode copilot AI. I straight-up do not know Python. The possible help someone would get from recovering a several hundred hour save is probably worth a few burned trees. If anyone who knows how to code wants to suggest an improvement of any sort, I'm all ears.

> This Readme was not generated by AI, though. I still know English.
