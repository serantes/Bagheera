# Bagheera Image Viewer User Manual

## 1. Introduction

Welcome to the Bagheera Image Viewer! This application is designed to help you browse, organize, and manage your image collection efficiently, with a focus on performance and integration with Baloo, KDE's file indexing service. Bagheera provides a fast, virtualized thumbnail grid, advanced filtering capabilities, duplicate detection, and a feature-rich image viewer.

### Key Features:

* **Fast Thumbnail Grid**: Browse large image collections with a responsive, virtualized view.
* **Advanced Filtering**: Filter images by filename, tags (including hierarchical tags), and metadata.
* **Baloo Integration**: Leverage Baloo's indexing for quick tag management and metadata retrieval.
* **Duplicate Detection**: Find and manage duplicate images using various methods.
* **Customizable Layouts**: Save and restore your window and viewer arrangements.
* **Image Viewer**: A dedicated viewer with navigation, zoom, slideshow, and image manipulation tools.
* **Region Detection**: Automatically detect and tag faces and pets, but also you can manually add bodies, objects, and landmarks regions in your images.
* **Keyboard Shortcuts**: Fully customizable shortcuts for efficient workflow.
* **File System Watcher**: Automatically updates the view when files are added, modified, or deleted externally.

## 2. Main Interface Overview

The main window of Bagheera Image Viewer consists of several key areas:

### 2.1. Search Bar

Located at the top of the window, the search bar allows you to:

* **Enter Search Queries**: Type keywords, tags (e.g., `tags=landscape`), or specific Bagueera queries.
* **Enter File Paths**: Directly type a directory path to scan, or a file path to open it in the viewer.
* **Browse Button**: Opens a file dialog to select an image to scan.

### 2.2. Thumbnail Grid

The central area displays your images as thumbnails. This view is virtualized, meaning it can handle thousands of images without performance degradation.

* **Selection**: Click on a thumbnail to select it. Use `Ctrl+Click` for multiple selections, and `Shift+Click` for range selection.
* **Double-Click**: Double-clicking a thumbnail opens it in the dedicated Image Viewer.
* **Context Menu**: Right-clicking on a thumbnail or a group header brings up a context menu with various actions (see Section 5).

### 2.3. Status Bar

At the bottom of the window, the status bar provides feedback on application activity:

* **Status Label**: Displays messages like "Ready", "Loading...", "Done", or error messages.
* **Progress Bar**: Shows the progress of ongoing operations like scanning or duplicate detection.
* **File System Watcher Indicator**: A small icon (e.g., folder-open) indicates if the file system watcher is actively monitoring directories.
* **Filtered Count**: Shows how many images are currently visible after applying filters.

### 2.4. Bottom Controls

Next to the status bar, you'll find controls for managing the thumbnail view:

* **Load More Images Button**: (Hidden by default, appears when more images are available) Loads the next batch of images from the current scan.
* **Load All Images Button**: (Hidden by default, appears when more images are available) Continuously loads all remaining images from the current scan.
* **Cancel Duplicates Button**: (Only visible during duplicate detection) Stops the ongoing duplicate detection process.
* **View Mode Dropdown**: Changes how images are grouped in the grid:
  * **Flat**: No grouping, all images displayed in a single list.
  * **Separate by Folder**: Groups images by their parent directory.
  * **Separate by Day/Week/Month/Year**: Groups images by their modification date.
  * **Separate by Rating**: Groups images by their star rating.
* **Sort Dropdown**: Changes the sorting order of images:
  * **Name ↑ / Name ↓**: Sorts alphabetically by filename (ascending/descending).
  * **Date ↑ / Date ↓**: Sorts by modification date (oldest/newest first).
* **Thumbnail Size Slider**: Adjusts the size of the thumbnails in the grid.
* **Size Label**: Displays the current thumbnail size in pixels.

## 3. Sidebar Docks

The main window features a dockable sidebar (initially hidden) that provides access to various tools and information. You can toggle its visibility via the main menu or keyboard shortcut.

### 3.1. Tags Tab

This tab allows you to view and edit tags associated with the currently selected images.

* **Tag Tree View**: Displays a hierarchical list of tags.
  * **⭐ USED TAGS**: Shows tags currently applied to the selected images.
  * **📂 ALL TAGS**: Shows all available tags from your Baloo index.
* **Search Bar**: Filters the tags displayed in the tree view.
* **Add Tag Button (`+`)**: Opens a dialog to create a new tag. You can use `/` to create hierarchical tags (e.g., `Nature/Animals`).
* **Refresh Tags Button**: Reloads the list of available tags from the Baloo database.
* **Apply Changes Button**: Saves any changes made to the tags of the selected images.
* **Ctrl+Click on Tag**: Forcefully toggles the check state of a tag, allowing you to mark it as added or removed even if it's already in that state for some files.
* **Tag Context Menu**: Right-click on a tag in the tree view for options:
  * **Search by this tag**: Performs a search for images with this specific tag.
  * **Add AND this tag to search**: Adds the tag to your current search query using an `AND` operator.
  * **Add OR this tag to search**: Adds the tag to your current search query using an `OR` operator.
* The text font style and color convey specific information about the state of each tag:
  * Italic Font: Indicates that the tag is not applied to all currently selected files (partial selection).
  * Blue Text: Indicates that the tag change is pending and has not yet been saved to the file's metadata.

### 3.2. Information Tab

This tab displays and allows editing of general information for the selected images.

* **Rating**: Assign a star rating (0-5 stars) to your images. Click on a star to cycle its state (Off -> Full -> Half -> Off).
* **Comment**: Add or edit a user comment for the selected images.
* **Apply Changes Button**: Saves any changes made to the rating or comment. This button is hidden if there are no changes.

### 3.3. Filter Tab

This tab helps you filter the images displayed in the thumbnail grid.

* **Filter by Filename Input**: Type text to filter images by their filename (case-insensitive).
* **Filter Mode (AND/OR)**:
  * **AND**: Images must have ALL selected tags to be shown.
  * **OR**: Images must have AT LEAST ONE of the selected tags to be shown.
* **Invert Button**: Inverts the selection of tags in the list below.
* **Filter Stats Label**: Shows how many items are hidden by the current filters.
* **Tag Search Input**: Filters the list of tags in this panel.
* **Tags List**: A table listing all unique tags found in your collection.
  * **Tag Column**: Check the box to include images with this tag.
  * **NOT Column**: Check the box to exclude images with this tag. (Checking one will uncheck the other in the same row).

### 3.4. Favorites Tab

Save and manage your frequently used search queries.

* **Search Bar**: Filters your list of favorite queries.
* **Favorites Table**: Lists your saved queries with a comment, the query itself, and an optional keyboard shortcut.
* **Load Button**: Executes the selected favorite query.
* **Add Button**: Adds the current search bar content as a new favorite. You'll be prompted for a comment.
* **Rename Button**: Edits the comment for the selected favorite.
* **Shortcut Button**: Assigns a global keyboard shortcut to the selected favorite query.
* **Delete Button**: Removes the selected favorite.
* **Move Up/Down Buttons**: Reorders your favorite queries in the list.

### 3.5. Layouts Tab (X11 only)

This tab allows you to save and restore the arrangement of your main window and any open image viewers. This feature is currently only available on X11display servers because Wayland does not support set window positions programatically.

* **Layouts Table**: Lists your saved layouts with their names and last modified dates.
* **Load Button**: Restores the selected layout.
* **Create Button**: Saves the current window arrangement as a new layout. You'll be prompted for a name.
* **Save Button**: Overwrites the selected layout with the current window arrangement.
* **Rename Button**: Renames the selected layout.
* **Copy Button**: Creates a copy of the selected layout with a new name.
* **Delete Button**: Deletes the selected layout file.

### 3.6. History Tab

Keeps a record of your past searches and opened files/directories.

* **History Table**: Lists your browsing history with the query/path and the date it was accessed.
* **Double-Click**: Re-executes the selected history entry.
* **Clear All Button**: Clears the entire history.
* **Delete Selected Button**: Removes the selected entry from history.
* **Delete Older Button**: Removes the selected entry and all older entries from history.

## 4. Image Viewer

The Image Viewer is a separate window that opens when you double-click a thumbnail or open a single image file.

### 4.1. Navigation

* **Next/Previous Image**: Use the arrow keys, mouse wheel, or dedicated buttons/shortcuts to move through images in the current list.
* **First/Last Image**: Jump to the beginning or end of the image list.

### 4.2. Zooming

* **Zoom In/Out**: Use `+`/`-` keys, mouse wheel (with `Ctrl`), or menu options.
* **Reset Zoom**: Resets the image to 100% or fits it to the screen.

### 4.3. Fullscreen Mode

Toggle fullscreen mode to view images without distractions.

### 4.4. Slideshow

* **Start/Stop Slideshow**: Automatically cycles through images at a configurable interval.
* **Reverse Slideshow**: Cycles through images in reverse order.
* **Set Interval**: Configure the delay between images in the slideshow.

### 4.5. Filmstrip

A small strip of thumbnails at the bottom, left, top, or right of the viewer, showing nearby images in the list.

* **Toggle Filmstrip**: Show or hide the filmstrip.
* **Filmstrip Position**: Configure its position in the Settings.

### 4.6. Region Detection

Bagheera can detect and tag specific areas within your images.

* **Detect Faces/Pets**: Automatically identifies these features.
* **Add Face/Pet/Body/Object/Landmark**: Manually define and name an area.
* **Show Faces & other areas**: Toggles the visibility of bounding boxes around detected regions.
* **Rename Region**: Rename an existing detected region.
* **Delete Region**: Remove a detected region.

### 4.7. Image Manipulation

* **Rotate Right/Left**: Rotates the image by 90 degrees clockwise or counter-clockwise in the viewer without modify the image.
* **Flip Horizontal/Vertical**: Flips the image along its horizontal or vertical axis.
* **Crop Mode**: Enter cropping mode to select a region of the image. Use Shift + mouse to maintain selection aspect ratio.
* **Save Cropped Image**: Saves the selected cropped region as a new image.

### 4.8. File Operations

* **Rename**: Renames the currently viewed image.
* **Move to Trash**: Moves the image to the system trash.
* **Delete Permanently**: Deletes the image permanently (bypassing trash).
* **Copy Image to Clipboard**: Copies the image data to the clipboard.
* **Copy File Path**: Copies the full path of the image to the clipboard.
* **Open with other application**: Opens a submenu to choose an external application to open the image.

### 4.9. Properties Dialog

Opens a dialog displaying detailed information about the image, including general file properties, metadata, and EXIF data. You can also add/edit extended attributes here.

## 5. Context Menus

### 5.1. Thumbnail Grid Context Menu (Right-click on a thumbnail)

* **View**: Opens the selected image in the Image Viewer.
* **Selection Submenu**:
  * **Select All**: Selects all visible thumbnails.
  * **Select None**: Clears the current selection.
  * **Invert Selection**: Inverts the current selection.
* **Open Submenu**:
  * **Open in Fullscreen Viewer**: Opens the image in the viewer in fullscreen.
  * **Open and search location**: Scans the directory containing the image and applies it as the current search.
  * **Open location with default application**: Opens the image's directory in your system's default file manager.
  * **Open with other application...**: Provides a list of applications associated with the image's MIME type.
* **Rename...**: Renames the selected image.
* **Move to...**: Moves the selected image to a new location.
* **Copy to...**: Copies the selected image to a new location.
* **Rotate Submenu**:
  * **Left**: Rotates the image 90 degrees counter-clockwise. This option modified the image.
  * **Right**: Rotates the image 90 degrees clockwise. . This option modified the image.
* **Move to Trash**: Moves the image to the system trash.
* **Delete**: Deletes the image permanently.
* **Clipboard Submenu**:
  * **Copy Image to Clipboard**: Copies the image data.
  * **Copy File Path**: Copies the full path of the image.
  * **Copy Directory Path**: Copies the path of the image's directory.
* **Regenerate Thumbnail**: Forces the regeneration of the thumbnail for the selected image.
* **Properties**: Opens the Properties dialog for the selected image.

### 5.2. Group Header Context Menu (Right-click on a group header)

* **Collapse/Expand Group**: Toggles the visibility of images within that group.

## 6. Main Menu Options

The main menu is accessed via the application menu button (usually a  three points icon or similar) in the top bar.

### 6.1. Cache Management

* **Clear cache (X items, Y MB, Z MB on disk)**: Clears the entire in-memory and on-disk thumbnail cache. This action is irreversible.
* **Clean up invalid cache entries**: Removes entries from the cache that no longer correspond to existing files.
* **Clean up stale metadata cache**: Removes outdated metadata entries from the cache.
* **Clean up stale directory cache**: Removes outdated directory entries from the cache.

### 6.2. Duplicate Detection

(Requires `imagehash` library to be installed)

* **Detect in current search**: Finds duplicate images only among the images currently displayed in the thumbnail grid.
* **Force full analysis**: Forces a complete re-analysis of hashes for the current search, even if cached data exists.
* **Detect all**: Scans predefined whitelist directories (configured in Settings) for duplicates, excluding blacklisted paths.
* **Force full all analysis**: Forces a complete re-analysis of hashes for all whitelisted directories.
* **Review ignored**: Opens a dialog to review and manage previously ignored duplicate pairs.
* **Clean up**: Removes stale hash entries from the duplicate database.
* **Repair index**: Rebuilds the internal index (BK-Tree) used for duplicate detection.
* **Clear ignored pairs**: Clears the list of all ignored duplicate pairs.
* **Clear hashes (X items, Y MB on disk)**: Deletes the entire duplicate hash database. This action is irreversible.

### 6.3. Settings

Opens the Settings dialog (see Section 7).

### 6.4. Language

Allows you to change the application's display language. A restart is required for changes to take full effect.

### 6.5. About

Displays information about the Bagheera Image Viewer, including its version and author.

## 7. Settings

The Settings dialog (accessible via the main menu) allows you to customize various aspects of Bagheera's behavior.

### 7.1. Scanner

* **Scan Max Level**: Maximum directory depth to scan recursively.
* **Scan Batch Size**: Number of images to load in each batch during scanning.
* **Scan Full On Start**: Automatically scan all images in the folder on startup.
* **Generation Threads**: Maximum number of simultaneous threads to generate thumbnails.
* **File search engine**: Engine to use for finding files. 'Bagheera' uses the BagheeraSearch library. 'Baloo' uses the 'baloosearch' command.

### 7.2. Regions

Configure settings related to face, pet, body, object, and landmark detection.

* **[Region Type] tags**: Default tags to apply for detected regions (e.g., `Person` for faces).
* **[Region Type] Detection Engine**: Library used for detection (e.g., MediaPipe for faces).
* **[Region Type] box color**: Color of the bounding box drawn around detected regions.
* **Max [Region Type] history**: Maximum number of recently used names to remember for autocompletion.
* **Use last name by default**: Automatically fill the assignment window with the last used name.
* **Reset to 'Face' after selection**: Automatically switch back to 'Face' mode after adding a different region type (Pet, Body, etc.).
* **Download Model**: Button to download required models for MediaPipe detection.

### 7.3. Thumbnails

* **Thumbs refresh interval (ms)**: Delay before refreshing thumbnails after resizing.
* **Thumbnails background color**: Background color of the thumbnail grid view.
* **Thumbnails filename color**: Font color for filenames in thumbnails.
* **Thumbnails tags color**: Font color for tags in thumbnails.
* **Thumbnails rating color**: Color for rating stars in thumbnails.
* **Thumbnails filename font size**: Font size for filenames in thumbnails.
* **Thumbnails tags font size**: Font size for tags in thumbnails.
* **Filename lines**: Number of lines for the filename text under the thumbnail.
* **Tag lines**: Number of lines for the tags text under the thumbnail.
* **Tooltip background color**: Background color for tooltips on thumbnails.
* **Tooltip text color**: Text color for tooltips on thumbnails.
* **Show filename/rating/tags**: Toggle visibility of these elements under thumbnails.

### 7.4. Image Viewer

* **Viewer mouse wheel speed**: Adjusts how fast scrolling the mouse wheel changes images in the viewer.
* **Auto resize window on zoom**: Automatically resize the window when zooming or changing images, fitting to the content.
* **Filmstrip Position**: Sets the default position of the filmstrip in new viewer windows (Bottom, Left, Top, Right).

### 7.5. Duplicates

* **Method**: Select the method for duplicate detection. Only phash is available.
* **Similarity Threshold**: Set the similarity threshold (50-100%). Higher values mean images must be more similar to be considered duplicates.
* **Confirm before deleting duplicates**: Show a confirmation dialog before moving a duplicate image to the trash.
* **Whitelist (folders to include)**: Comma-separated paths of folders to scan when using 'Detect all'.
* **Blacklist (folders to exclude)**: Comma-separated paths of folders to ignore during 'Detect all' scans.
* **Delete button sends to trash by default**: If checked, pressing the Delete key will move files to the trash. If unchecked, it will permanently delete them.

## 8. Keyboard Shortcuts

Bagheera Image Viewer provides extensive keyboard shortcuts for efficient navigation and operation. You can view and customize these shortcuts via the main menu: `Menu Button > Configure Keyboard Shortcuts...`.

The shortcuts are categorized into "Global" (affecting the main window) and "Viewer" (affecting the image viewer).

### 8.1. Customizing Shortcuts

In the "Keyboard Shortcuts" dialog:

1. Double-click on an action's shortcut to edit it.
2. Press the desired key combination.
3. If a conflict is detected, you will be warned and can choose to override the existing shortcut.

## 9. Command Line Usage

You can launch Bagheera Image Viewer with specific arguments:

```bash
bagheeraview [file:/path_to_file | file:/directory | search:/query]
bagheeraview --x11 [file:/path_to_file | file:/directory | search:/query] # Force X11 platform (for layouts)
```
