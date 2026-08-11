# Minecraft World Sign Search Tool

This little tool searches every sign in a Minecraft world save and shows you what
they say and where they are. No Minecraft required, it just reads the world's save
files directly.

Works on any Minecraft world save for versions 1.13 through 1.20.x (including
the pre-1.18 and post-1.18 save format change). This README uses the
**Cubeville** world downloads (CV3 through CV7, plus Blipville) as the
walkthrough example since that's what it was originally written for, but the
script itself isn't tied to Cubeville at all, point it at the save folder of
any Minecraft world in that version range and it'll work the same way.

You do **not** need to know anything about coding to use this. Just follow the
steps below in order.

---

## Step 1: Get a world save

If you're grabbing a Cubeville world:

1. Go to the world downloads thread: https://cubeville-forum.org/viewtopic.php?f=3&t=3096
2. Click the Google Drive link for the world you want (for example "CV4").
3. On the Google Drive page, click the **Download** button (usually a down-arrow icon,
   or right-click the file and choose Download).
4. The file will download as a `.zip` file, probably into your **Downloads** folder.

If you're using a different Minecraft world (your own save, a friend's server
download, etc), just get it onto your computer however you normally would,
it just needs to end up as a folder containing a `region` subfolder. Then
skip to Step 2.

---

## Step 2: Unzip it somewhere easy to find

1. Find the `.zip` file you just downloaded (check your Downloads folder).
2. Right-click it and choose **Extract All...** (Windows) or double-click it (Mac).
3. When Windows asks where to extract it, pick your **Desktop** so it's easy to find.
   You should end up with a regular folder (not a zip) sitting on your Desktop,
   something like `Desktop\cv4`.
4. Open that folder and make sure you see folders inside it named things like
   `region`, `data`, `playerdata`, etc. If you see another folder with the same
   name inside it (like `cv4\cv4`), that inner one is the actual world folder,
   remember which one it is, you'll need its exact location in Step 5.

---

## Step 3: Install Python

If you already have Python installed, skip to Step 4.

1. Go to https://www.python.org/downloads/
2. Click the big yellow **Download Python** button.
3. Open the file you downloaded to install it.
4. **Important:** On the very first install screen, check the box that says
   **"Add Python to PATH"** before clicking Install. If you miss this, the
   commands in Step 5 won't work and you'll need to reinstall.
5. Click through the rest of the installer with the default options.

---

## Step 4: Get the script

1. Save the `search_signs.py` file (attached to this post/message) into the
   **same folder** as the world you unzipped. For example, if your world is at
   `Desktop\cv4\cv4`, put `search_signs.py` in `Desktop\cv4` (right next to the
   `cv4` folder, not inside it).
2. Open a terminal in that folder:
   - **Windows:** Open the folder in File Explorer, click in the empty address
     bar at the top (where the folder path is shown), type `powershell`, and
     press Enter. A black/blue terminal window will pop open already
     pointed at that folder.
   - **Mac:** Open the folder in Finder, right-click inside it (not on a file)
     and choose "New Terminal at Folder" (if you don't see this option, open
     Terminal normally and type `cd ` followed by dragging the folder into
     the window, then press Enter).

That's it, no extra packages to install, the script only uses what's
already built into Python.

---

## Step 5: Run the search

In that same terminal window, type the following and press Enter:

```
python search_signs.py "PATH_TO_YOUR_WORLD_FOLDER"
```

Replace `PATH_TO_YOUR_WORLD_FOLDER` with the actual folder path from Step 2.
For example:

```
python search_signs.py "C:\Users\nuumm\Desktop\cv4\cv4"
```

Tips for getting the exact path:
- In File Explorer, click into the folder, then click the address bar at the
  top, this shows/copies the full path.
- The folder you point to should be the one that directly contains a folder
  called `region` inside it.

Running it like this will print out **every single sign** in the world. That
can be a lot of text.

**Heads up on speed:** bigger, more-explored worlds take longer to scan
since there's just more map to read (a small world finishes in seconds, a
big one takes a bit longer). That's normal, just let it finish.

### Searching for a specific word

If you're looking for something specific (a username, a word, a place name),
add `--find` followed by what you're looking for in quotes:

```
python search_signs.py "C:\Users\nuumm\Desktop\cv4\cv4" --find "welcome"
```

This only shows signs that contain that word (it doesn't matter if it's
uppercase or lowercase).

---

## Reading the results

Each result looks like this:

```
(844, 65, -305)  ->  bmminecraft123 | 5 | B 2.98 | Iron Ore
```

- `(844, 65, -305)` is the in-game X, Y, Z coordinate of the sign.
- Everything after `->` is the actual text on the sign, with each line
  separated by `|`.

---

## Troubleshooting

- **"python is not recognized..."** — Python wasn't added to PATH during
  install. Reinstall Python (Step 3) and make sure to check the "Add Python
  to PATH" box.
- **"No 'region' folder found..."** — You're pointing the script at the wrong
  folder. Look for the folder that directly contains `region`, `data`,
  `playerdata`, etc, and use that exact path.
- **Nothing shows up for `--find`** — Double check spelling, and try a
  shorter/simpler word, since it has to match exactly (just not
  case-sensitive).

---

This works on both the old 1.16.5-era save format (pre-1.18 worlds) and the
1.18+ save format (including 1.20.4), no need to do anything differently
between them, the script figures out which format it's looking at
automatically.
