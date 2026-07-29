#!/usr/bin/env python3
"""
Space Engineers WGS Orphaned File Recovery Utility
Recovers unindexed WGS saves from Space Engineers local backup folders
"""

import argparse
import os
import re
import subprocess
import sys
import json
import struct
import uuid
import shutil
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple


class WGSRecoveryUtility:
    def __init__(self, package_root: Optional[str] = None):
        self.localappdata = (
            Path(package_root).expanduser()
            if package_root
            else Path.home() / "AppData" / "Local" / "Packages"
        )
        self.temp_dir = Path(tempfile.gettempdir())
        self.temp_thumb_dir = self.temp_dir / "wgsrecoverer_thumb"
        self.temp_thumb_path = self.temp_thumb_dir / "thumb.jpg"
        self.keen_packages = []
        self.selected_world = None
        self.custom_package_root = False
        self.scan_base_path = None

    def log(self, message: str, level: str = "INFO"):
        """Print diagnostic messages"""
        print(f"[{level}] {message}")

    def prompt_for_package_root(self):
        """Allow the user to override the package root for debugging."""
        response = input("\nEnter custom KeenSoftwareHouse package location (leave blank for default): ").strip()
        self.custom_package_root = bool(response)
        self.scan_base_path = None
        if response:
            self.localappdata = Path(response).expanduser()
            self.log(f"Using custom package location: {self.localappdata}")
        else:
            self.localappdata = Path.home() / "AppData" / "Local" / "Packages"
            self.log(f"Using default package location: {self.localappdata}")

    def locate_keen_packages(self) -> List[Path]:
        """Locate all KeenSoftwareHouse* packages"""
        self.log(f"Searching for KeenSoftwareHouse packages in {self.localappdata}")
        
        if not self.localappdata.exists():
            self.log(f"LocalAppData path does not exist: {self.localappdata}", "ERROR")
            return []

        packages = [p for p in self.localappdata.iterdir() 
                   if p.is_dir() and "KeenSoftwareHouse" in p.name]
        
        self.log(f"Found {len(packages)} KeenSoftwareHouse package(s)")
        return packages

    def find_nonempty_package(self, packages: List[Path]) -> Optional[Path]:
        """Find the first non-empty KeenSoftwareHouse package"""
        for package in packages:
            wgs_path = package / "SystemAppData" / "wgs"
            if wgs_path.exists() and any(wgs_path.iterdir()):
                self.log(f"Selected package: {package.name}")
                return package
        
        self.log("No non-empty KeenSoftwareHouse packages found", "ERROR")
        return None

    def is_container_filename(self, path: Path) -> bool:
        """Return True if the path is a container.<0-9999> file."""
        if not path.is_file() or not path.name.startswith("container."):
            return False

        number_text = path.name[len("container."):]
        if not number_text.isdigit():
            return False

        value = int(number_text)
        return 0 <= value <= 9999

    def find_container_files(self, folder: Path) -> List[Path]:
        """Return all valid container.<0-9999> files in a directory."""
        return [
            p for p in folder.iterdir()
            if p.is_file() and self.is_container_filename(p)
        ]

    def find_container_scan_root(self, start_path: Path) -> Optional[Path]:
        """Search for a directory containing container.<number> files up to a limited depth."""
        if not start_path.exists() or not start_path.is_dir():
            self.log(f"Search path does not exist: {start_path}", "ERROR")
            return None

        max_depth = 5 + len(start_path.parts)
        stack = [(start_path, 0)]

        while stack:
            current, depth = stack.pop()
            if not current.is_dir() or depth > max_depth:
                continue

            container_files = self.find_container_files(current)
            if container_files:
                scan_root = current.parent
                self.log(f"Found container files in {current}; using scan root {scan_root}")
                return scan_root

            for child in sorted(current.iterdir(), key=lambda p: p.name, reverse=True):
                if child.is_dir():
                    stack.append((child, depth + 1))

        self.log(f"No container.<number> files found under {start_path}", "WARN")
        return None

    def find_nonempty_wgs_folder(self, package: Path) -> Optional[Path]:
        """Find the non-empty folder in SystemAppData/wgs"""
        wgs_path = package / "SystemAppData" / "wgs"
        
        if not wgs_path.exists():
            self.log(f"WGS path does not exist: {wgs_path}", "ERROR")
            return None

        folders = [p for p in wgs_path.iterdir() if p.is_dir()]
        
        for folder in folders:
            if any(folder.iterdir()):
                self.log(f"Selected WGS folder: {folder.name}")
                return folder
        
        self.log("No non-empty WGS folders found", "ERROR")
        return None

    def find_containers(self, base_path: Path) -> List[Tuple[Path, str]]:
        """Find all folders with container.<0-9999> files"""
        containers = []
        
        if not base_path.exists():
            self.log(f"Base path does not exist: {base_path}", "ERROR")
            return containers

        for folder in base_path.iterdir():
            if not folder.is_dir():
                continue
            
            container_files = self.find_container_files(folder)
            if container_files:
                container_file = sorted(container_files, key=lambda p: p.name)[0].name
                containers.append((folder, container_file))
        
        self.log(f"Found {len(containers)} folder(s) with container files")
        return containers

    def validate_container_folder(self, folder: Path, container_file: str) -> bool:
        """Check if folder has container.# and at least 3 other files"""
        files = list(folder.glob("*"))
        file_count = len(files)
        
        if file_count < 4:  # container.# + 3 others
            self.log(f"Folder has insufficient files ({file_count} < 4): {folder.name}", "WARN")
            return False
        
        self.log(f"Folder validation passed ({file_count} files): {folder.name}")
        return True

    def read_utf16_fixed(self, data, chars: int) -> str:
        """Read UTF-16-LE fixed-width string from bytes or a binary stream."""
        if hasattr(data, "read"):
            raw_data = data.read(chars * 2)
        else:
            raw_data = data[: chars * 2]

        return raw_data.decode("utf-16-le").rstrip("\0")

    def parse_container(self, folder: Path, container_file: str) -> Optional[Dict]:
        """Parse container.# file and create manifest"""
        container_path = folder / container_file
        self.log(f"Parsing container: {container_path}")
        
        try:
            with open(container_path, "rb") as f:
                f.read(4)  # unknown header
                file_count = struct.unpack("<i", f.read(4))[0]
                
                entries = []
                
                for _ in range(file_count):
                    filename = self.read_utf16_fixed(f, 64)
                    guid1 = uuid.UUID(bytes_le=f.read(16)).hex.upper()
                    guid2 = uuid.UUID(bytes_le=f.read(16)).hex.upper()
                    
                    exists1 = (folder / guid1).exists()
                    exists2 = (folder / guid2).exists()
                    
                    if guid1 == guid2:
                        chosen = guid1
                    elif exists1 and not exists2:
                        chosen = guid1
                    elif exists2 and not exists1:
                        chosen = guid2
                    elif exists1 and exists2:
                        chosen = "AMBIGUOUS"
                    else:
                        chosen = "MISSING"
                    
                    entries.append({
                        "filename": filename,
                        "chosen_blob": chosen,
                        "guid1": guid1,
                        "guid2": guid2
                    })
                
                self.log(f"Successfully parsed {len(entries)} entries from container")
                return {"folder": folder, "entries": entries, "container_file": container_file}
        
        except Exception as e:
            self.log(f"Failed to parse container: {e}", "ERROR")
            return None

    def find_sandbox_config(self, entries: List[Dict]) -> Optional[str]:
        """Find the obscured sandbox config file GUID for any supported filename variant."""
        preferred_blob = None
        fallback_blob = None

        for entry in entries:
            filename = entry["filename"].lower()
            if "sandbox" not in filename or not filename.endswith(".sbc"):
                continue

            blob = entry["chosen_blob"]
            if blob in ["AMBIGUOUS", "MISSING"]:
                continue

            normalized = filename.replace("_", ".").replace("-", ".")
            if "sandbox.config" in normalized or "sandbox_config" in normalized:
                self.log(f"Resolved sandbox config blob: {blob} for file {entry['filename']}")
                return blob

            if fallback_blob is None:
                fallback_blob = blob

        return preferred_blob or fallback_blob

    def extract_session_name(self, folder: Path, sandbox_guid: str) -> Optional[str]:
        """Extract SessionName from Sandbox_config.sbc"""
        sandbox_path = folder / sandbox_guid
        
        if not sandbox_path.exists():
            self.log(f"Sandbox_config.sbc file not found: {sandbox_path}", "ERROR")
            return None
        
        try:
            tree = ET.parse(sandbox_path)
            root = tree.getroot()
            
            session_name_elem = root.find(".//SessionName")
            if session_name_elem is not None and session_name_elem.text:
                session_name = session_name_elem.text.strip()
                self.log(f"Extracted SessionName: {session_name}")
                return session_name
            else:
                self.log("SessionName field not found in XML", "ERROR")
                return None
        
        except ET.ParseError as e:
            self.log(f"Malformed XML in Sandbox_config.sbc: {e}", "ERROR")
            return None
        except Exception as e:
            self.log(f"Failed to read Sandbox_config.sbc: {e}", "ERROR")
            return None

    def scan_worlds(self, base_path: Path) -> List[Dict]:
        """Scan and list all recoverable worlds"""
        self.log("Starting world scan...")
        
        containers = self.find_containers(base_path)
        worlds = []
        
        for folder, container_file in containers:
            self.log(f"Processing folder: {folder.name}")
            
            if not self.validate_container_folder(folder, container_file):
                continue
            
            parsed = self.parse_container(folder, container_file)
            if not parsed:
                continue
            
            sandbox_guid = self.find_sandbox_config(parsed["entries"])
            if not sandbox_guid:
                self.log(f"No Sandbox_config.sbc found in {folder.name}. Skipping folder.", "WARN")
                continue
            
            session_name = self.extract_session_name(folder, sandbox_guid)
            if not session_name:
                continue
            
            file_count = len(list(folder.glob("*")))
            world_info = {
                "folder": folder,
                "folder_name": folder.name,
                "session_name": session_name,
                "file_count": file_count,
                "entries": parsed["entries"],
                "container_file": container_file
            }
            
            worlds.append(world_info)
        
        return worlds

    def display_worlds(self, worlds: List[Dict]):
        """Display list of recoverable worlds"""
        print("\n" + "="*70)
        print("RECOVERABLE WORLDS")
        print("="*70)
        
        if not worlds:
            print("No recoverable worlds found.")
            return
        
        for idx, world in enumerate(worlds, 1):
            world_size = self.get_world_size(world)
            latest_timestamp = self.get_latest_timestamp(world)
            print(f"\n[{idx}] {world['session_name']}")
            print(f"    Blob folder: {world['folder_name']}")
            print(f"    Files: {world['file_count']}")
            print(f"    Size: {self.format_size(world_size)}")
            print(f"    Latest timestamp: {self.format_timestamp(latest_timestamp)}")
            print(f"    Path: {world['folder']}")
        
        print("\n" + "="*70)

    def select_world(self, worlds: List[Dict]) -> Optional[Dict]:
        """Allow user to select a world"""
        if not worlds:
            return None
        
        while True:
            try:
                print(f"\nSelect a world [1-{len(worlds)}] to inspect or recover. [0] to exit: ")
                choice = int(input("Enter selection: "))
                if choice == 0:
                    self.log("World selection cancelled by user")
                    return None
                if 1 <= choice <= len(worlds):
                    return worlds[choice - 1]
                else:
                    print(f"Invalid selection. Please enter 0 or 1-{len(worlds)}")
            except ValueError:
                print("Invalid input. Please enter a number.")

    def save_manifest(self, entries: List[Dict]) -> Path:
        """Save manifest.json to temp directory"""
        manifest_path = self.temp_dir / "manifest.json"
        
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=4)
        
        self.log(f"Manifest saved to: {manifest_path}")
        return manifest_path

    def handle_manifest_action(self, manifest_path: Path, output_base: Optional[Path] = None):
        """Ask what to do with the generated manifest.json file."""
        if not manifest_path.exists():
            self.log("Manifest file does not exist; nothing to do.", "WARN")
            return

        print("\nManifest options:")
        if output_base is not None:
            print("  [1] Add manifest to the parent directory of the recovered world folder")
        print("  [2] Add manifest to a given directory")
        print("  [3] Print manifest and then delete it")
        print("  [4] Delete it")

        while True:
            choice = input("\nWhat do you want to do with manifest.json? ").strip()
            if output_base is None and choice == "1":
                print("Option 1 is not available without a recovered world output folder.")
                continue

            if choice in ["1", "2", "3", "4"]:
                self.log(f"Manifest action selected: {choice}")
                break
            print("Invalid selection. Please enter 1-4.")

        try:
            if choice == "1":
                destination = output_base / "manifest.json"
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(manifest_path, destination)
                self.log(f"Manifest copied to: {destination}")
            elif choice == "2":
                destination_text = input("Enter destination path for manifest.json: ").strip()
                if not destination_text:
                    self.log("No destination provided; manifest was not copied.", "WARN")
                    return

                destination = Path(destination_text).expanduser()
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(manifest_path, destination)
                self.log(f"Manifest copied to: {destination}")
            elif choice == "3":
                print(manifest_path.read_text(encoding="utf-8"))
            else:
                self.log("Manifest delete selected")

            manifest_path.unlink(missing_ok=True)
            self.log(f"Manifest deleted: {manifest_path}")
        except Exception as e:
            self.log(f"Failed to process manifest: {e}", "ERROR")

    def format_size(self, size_bytes: int) -> str:
        """Format a byte size into a human-readable string."""
        units = ["B", "KB", "MB", "GB", "TB"]
        size = float(size_bytes)
        for unit in units:
            if size < 1024 or unit == units[-1]:
                if unit == "B":
                    return f"{int(size)} B"
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"

    def format_timestamp(self, timestamp: Optional[float]) -> str:
        """Format an epoch timestamp into a human-readable string."""
        if timestamp is None:
            return "N/A"
        try:
            return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return "N/A"

    def get_latest_timestamp(self, world: Dict) -> Optional[float]:
        """Return the latest modification time among the available blobs for a world."""
        timestamps = []
        for entry in world["entries"]:
            blob = entry["chosen_blob"]
            if blob in ["AMBIGUOUS", "MISSING"]:
                continue
            file_path = world["folder"] / blob
            if file_path.exists() and file_path.is_file():
                timestamps.append(file_path.stat().st_mtime)
        return max(timestamps) if timestamps else None

    def get_world_size(self, world: Dict) -> int:
        """Calculate the total size of the selected world from the resolved blob files."""
        total = 0
        for entry in world["entries"]:
            blob = entry["chosen_blob"]
            if blob in ["AMBIGUOUS", "MISSING"]:
                continue
            file_path = world["folder"] / blob
            if file_path.exists() and file_path.is_file():
                total += file_path.stat().st_size
        return total

    def get_world_warning_messages(self, world: Dict) -> List[str]:
        """Return warning messages for missing or incomplete world files."""
        critical_names = {
            "sandbox_0_0_0_.sbs",
            "sandbox_0_0_0_.sbsb5",
            "sandbox.sbc",
        }
        missing_entries = []
        missing_critical = []
        indexed_critical = []

        for entry in world["entries"]:
            filename = entry["filename"]
            blob = entry["chosen_blob"]
            file_path = world["folder"] / blob if blob not in ["AMBIGUOUS", "MISSING"] else None
            exists = False
            if file_path is not None and file_path.exists() and file_path.is_file():
                exists = True

            normalized_name = filename.lower()
            if normalized_name in critical_names:
                indexed_critical.append(filename)

            if not exists:
                missing_entries.append(entry)
                if normalized_name in critical_names:
                    missing_critical.append(filename)

        if not missing_entries and indexed_critical:
            return []

        warnings = ["WARNING: Some files referenced by the container are missing from the blob folder."]
        if missing_critical:
            critical_names_text = sorted(set(missing_critical))
            warnings.append(f"Critical files missing: {', '.join(critical_names_text)}")
            warnings.append("This save is missing critical files and is likely invalid.")
        elif indexed_critical:
            warnings.append("The save appears incomplete, but the missing files are not critical.")
            warnings.append("You may not be able to load this world in Space Engineers as-is, and may require additional debugging not provided by this utility.")
        else:
            warnings.append("The container does not contain any critical world files.")
            warnings.append("This save is likely invalid.")

        return warnings

    def list_world_contents(self, world: Dict):
        """Display decoded contents of selected world"""
        self.log(f"Listing world contents for: {world['session_name']}")
        world_size = self.get_world_size(world)
        print("\n" + "="*70)
        print(f"CONTENTS OF: {world['session_name']} ({self.format_size(world_size)})")
        latest_timestamp = self.get_latest_timestamp(world)
        print(f"Most recent timestamp: {self.format_timestamp(latest_timestamp)}")
        print("="*70 + "\n")

        warnings = self.get_world_warning_messages(world)
        if warnings:
            for warning in warnings:
                print(warning)

        for idx, entry in enumerate(world['entries'], 1):
            filename = entry['filename']
            blob = entry['chosen_blob']
            file_path = world["folder"] / blob if blob not in ["AMBIGUOUS", "MISSING"] else None
            exists = False
            if file_path is not None and file_path.exists() and file_path.is_file():
                exists = True

            status = "✓" if exists else "⚠"
            file_size = ""
            timestamp_text = ""
            if exists and file_path is not None:
                file_stat = file_path.stat()
                file_size = f" ({self.format_size(file_stat.st_size)})"
                timestamp_text = f" @ {self.format_timestamp(file_stat.st_mtime)}"
            print(f"[{status}] {idx:3d}. {filename}{file_size}{timestamp_text}")
            if blob == "AMBIGUOUS":
                print(f"         AMBIGUOUS: {entry['guid1']} or {entry['guid2']}")
            elif blob == "MISSING":
                print(f"         MISSING: {entry['guid1']} or {entry['guid2']}")
        
        print("\n" + "="*70)

    def cleanup_temp_thumb(self):
        """Remove the temporary thumbnail file created for viewing."""
        if self.temp_thumb_path.exists():
            self.temp_thumb_path.unlink(missing_ok=True)
            self.log(f"Deleted temporary thumbnail: {self.temp_thumb_path}")

        if self.temp_thumb_dir.exists() and self.temp_thumb_dir.is_dir():
            try:
                if not any(self.temp_thumb_dir.iterdir()):
                    self.temp_thumb_dir.rmdir()
            except Exception:
                pass

    def display_world_thumb(self, world: Dict):
        """Copy the world thumb.jpg blob to a temp file, rename it, and open it."""
        thumb_entry = None
        for entry in world["entries"]:
            if entry["filename"].lower() == "thumb.jpg":
                thumb_entry = entry
                break

        if thumb_entry is None:
            self.log("No thumb.jpg entry found in this world", "WARN")
            print("No thumb.jpg entry was found for this world.")
            return

        blob = thumb_entry["chosen_blob"]
        if blob in ["AMBIGUOUS", "MISSING"]:
            self.log(f"thumb.jpg blob is unavailable: {blob}", "WARN")
            print("The thumb.jpg blob is ambiguous or missing and cannot be displayed.")
            return

        source_path = world["folder"] / blob
        if not source_path.exists():
            self.log(f"Thumbnail source file not found: {source_path}", "ERROR")
            print("The thumbnail blob file does not exist on disk.")
            return

        self.cleanup_temp_thumb()
        self.temp_thumb_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, self.temp_thumb_path)
        self.log(f"Prepared temporary thumbnail: {self.temp_thumb_path}")

        try:
            if hasattr(os, "startfile"):
                os.startfile(str(self.temp_thumb_path))  # type: ignore[attr-defined]
            else:
                opener = "open" if sys.platform == "darwin" else "xdg-open"
                subprocess.run([opener, str(self.temp_thumb_path)], check=False)
            print("Opened thumb.jpg in the default image viewer.")
        except Exception as e:
            self.log(f"Failed to open thumbnail: {e}", "ERROR")
            self.cleanup_temp_thumb()

    def sanitize_folder_name(self, name: str) -> str:
        """Remove Windows-invalid filename characters and trailing spaces/periods."""
        sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", name)
        sanitized = sanitized.rstrip(" .")
        if sanitized != name:
            self.log(f"World name invalid for folder name, sanitizing: '{name}' -> '{sanitized}'", "INFO")
        return sanitized or "RecoveredWorld"

    def recover_world(self, world: Dict, output_base: Path, use_default_output: bool = False):
        """Recover world using reconstructor logic"""
        self.log(f"Recovering world: {world['session_name']}")
        
        # Create output directory
        folder_name = self.sanitize_folder_name(world['session_name'])
        output_dir = output_base / folder_name
        output_dir.mkdir(parents=True, exist_ok=True)
        self.log(f"Output directory: {output_dir}")
        
        blob_folder = world['folder']
        entries = world['entries']
        
        copied = 0
        skipped = 0
        
        for entry in entries:
            filename = entry['filename']
            guid1 = entry['guid1'].upper()
            guid2 = entry['guid2'].upper()
            
            file1 = blob_folder / guid1
            file2 = blob_folder / guid2
            
            exists1 = file1.exists()
            exists2 = file2.exists()
            
            # Case 1: Both GUIDs identical
            if guid1 == guid2:
                if not exists1:
                    self.log(f"SKIPPED: {filename} (GUID not found)", "WARN")
                    skipped += 1
                    continue
                chosen = file1
            
            # Case 2: GUIDs differ
            else:
                if exists1 and not exists2:
                    chosen = file1
                elif exists2 and not exists1:
                    chosen = file2
                elif exists1 and exists2:
                    self.log(f"SKIPPED: {filename} (AMBIGUOUS)", "WARN")
                    skipped += 1
                    continue
                else:
                    self.log(f"SKIPPED: {filename} (MISSING)", "WARN")
                    skipped += 1
                    continue
            
            # Copy file
            destination = output_dir / filename
            destination.parent.mkdir(parents=True, exist_ok=True)
            
            try:
                shutil.copy2(chosen, destination)
                copied += 1
                self.log(f"Recovered: {filename}")
            except Exception as e:
                self.log(f"Failed to copy {filename}: {e}", "ERROR")
                skipped += 1
        
        print("\n" + "="*70)
        print(f"RECOVERY SUMMARY")
        print("="*70)
        print(f"Recovered: {copied} files")
        print(f"Skipped:   {skipped} files")
        print(f"Output:    {output_dir.resolve()}")
        print("‒"*70)
        warnings = self.get_world_warning_messages(world)
        for warning in warnings:
            print(warning)
        if warnings:
            print("‒"*70)
        if use_default_output:
            print("Remember to turn off cloud-saving in game settings to see saves added locally!")
            print("To cloud sync your recovered world: Enable cloud syncing while in the world, then save.")
        else:
            print("See readme for help re-cloud-syncing the save.")
        print("="*70 + "\n")
        self.log(f"Recovery complete for {world['session_name']}: recovered={copied}, skipped={skipped}")

        try:
            if hasattr(os, "startfile"):
                os.startfile(str(output_dir))  # type: ignore[attr-defined]
            else:
                opener = "open" if sys.platform == "darwin" else "xdg-open"
                subprocess.run([opener, str(output_dir)], check=False)
            self.log(f"Opened recovered world folder: {output_dir}")
        except Exception as e:
            self.log(f"Failed to open recovered world folder: {e}", "ERROR")
        

    def run(self):
        """Main execution flow"""
        self.log("Space Engineers WGS Recovery Utility Started")
        
        while True:
            # Allow an override for debugging
            self.prompt_for_package_root()

            # Locate packages
            packages = self.locate_keen_packages()
            if packages:
                # Find non-empty package
                package = self.find_nonempty_package(packages)
                if not package:
                    return
                
                # Find WGS folder
                wgs_folder = self.find_nonempty_wgs_folder(package)
                if not wgs_folder:
                    return
                
                scan_root = wgs_folder
                break

            if not self.custom_package_root:
                self.log("No packages found. Exiting.", "ERROR")
                return

            self.log("No KeenSoftwareHouse packages found at the custom location.")
            print("\nA blind search can be performed to locate WGS save folders stored somewhere other than the predefined search location.")
            print("\nNOTE: A blind search is not guaranteed to find all save locations.")
            print("It only searches 5 folders deep for the first directory that contains a valid save, then stops.")
            print("The blind search option is only recommended for backups or copies of the WGS system inside of the KeenSoftwareHouse package.")
            print("If other packages are present, it will likely fail.")
            print("It may also discover saves in the Recycle Bin for non C: drives.")
            blind_search = input("Would you like to perform a blind search for save locations? [y/N]: ").strip().lower()
            if blind_search in ["y", "yes"]:
                scan_root = self.find_container_scan_root(self.localappdata)
                if not scan_root:
                    self.log("No container roots found. Returning to package location prompt.", "WARN")
                    continue
                self.scan_base_path = scan_root
                break

            self.log("Blind search cancelled. Returning to package location prompt.")

        # Scan worlds
        worlds = self.scan_worlds(scan_root)
        if not worlds:
            self.log("No recoverable worlds found.", "ERROR")
            return
        
        self.log(f"Found {len(worlds)} recoverable world(s)")
        
        # Display worlds
        self.display_worlds(worlds)

        world = self.select_world(worlds)
        if not world:
            return

        self.log(f"Selected world: {world['session_name']} ({world['folder']})")

        self.list_world_contents(world)

        while True:
            print("\nOptions for selected world:")
            print("  [1] Select directory to recover world to")
            print("  [2] Display thumb.jpg")
            print("  [3] Exit")

            choice = input("\nSelect an option [1-3]: ").strip()
            self.log(f"Selected menu option: {choice}")

            if choice == "1":
                self.cleanup_temp_thumb()
                manifest_path = self.save_manifest(world['entries'])
                output_path_text = input(
                    "Enter output directory path. Leave empty for default Space Engineers save location: "
                ).strip()
                if output_path_text:
                    output_base = Path(output_path_text).expanduser()
                    using_default_output = False
                else:
                    output_base = Path(os.path.expandvars(r"%APPDATA%\SpaceEngineers\Saves")).expanduser()
                    using_default_output = True

                self.log(f"Recovery output base selected: {output_base}")

                if not output_base.exists():
                    try:
                        output_base.mkdir(parents=True, exist_ok=True)
                        self.log(f"Created output directory: {output_base}")
                    except Exception as e:
                        self.log(f"Output directory could not be created: {e}", "ERROR")
                        return

                self.recover_world(world, output_base, use_default_output=using_default_output)
                self.handle_manifest_action(manifest_path, output_base=output_base)
                return

            if choice == "2":
                self.cleanup_temp_thumb()
                self.display_world_thumb(world)
                continue

            if choice == "3":
                self.cleanup_temp_thumb()
                return

            print("Invalid selection. Please enter 1-3.")


def main():
    parser = argparse.ArgumentParser(description="Recover orphaned Space Engineers WGS files")
    parser.add_argument(
        "--package-root",
        help="Override the package root directory to scan (for debugging)",
    )
    args = parser.parse_args()

    utility = None
    try:
        utility = WGSRecoveryUtility(package_root=args.package_root)
        utility.run()
    except KeyboardInterrupt:
        print("\n\nOperation cancelled by user.")
        sys.exit(0)
    except Exception as e:
        print(f"\n[FATAL] Unexpected error: {e}")
        if utility is not None:
            manifest_path = utility.temp_dir / "manifest.json"
            if manifest_path.exists():
                manifest_path.unlink(missing_ok=True)
                utility.log(f"Manifest deleted on error: {manifest_path}")
        sys.exit(1)
    finally:
        if utility is not None:
            manifest_path = utility.temp_dir / "manifest.json"
            if manifest_path.exists():
                manifest_path.unlink(missing_ok=True)
                utility.log(f"Manifest deleted on exit: {manifest_path}")
            utility.cleanup_temp_thumb()


if __name__ == "__main__":
    main()
