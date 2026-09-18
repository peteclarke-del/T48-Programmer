# Installing T48 Programmer for linux

## Release package

The package targets 64-bit Ubuntu 24.04 and Linux Mint 22. It contains the
application, its user guide, minipro 0.7.4 compiled from source, minipro's chip
database, and the udev rules for XGecu programmers. The distribution supplies
Python, GTK 4, libadwaita, PyGObject and libusb.

1. Download `T48-Programmer_0.1.0_ubuntu24.04_amd64.deb` and `SHA256SUMS` from the release
   into the same folder.
2. Verify the download:

   ```sh
   sha256sum --check --ignore-missing SHA256SUMS
   ```

3. Install the package and its dependencies:

   ```sh
   sudo apt install ./T48-Programmer_0.1.0_ubuntu24.04_amd64.deb
   ```

4. Unplug the programmer and plug it in again. The package reloads the udev
   rules, but they are applied when a device appears, so a programmer that was
   already connected keeps its old permissions until it is replugged.
5. Start **T48 Programmer** from the application grid, or run `t48-programmer`.

The bundled minipro lives in `/usr/lib/t48-programmer/bin` and is used in
preference to any other on the system, so the version that runs is the version
the package was tested with. A minipro installed from your distribution is left
alone and the two do not conflict.

## Upgrading

Choose **Help, Check for Application Updates**. When GitHub has a newer release,
**Update to** downloads the package made for the same system as the installed
one, checks it against the release's `SHA256SUMS`, and installs it with
`pkexec apt-get install` after the system asks for your password. It then
offers to restart the application. The check sends one request to
api.github.com, and only when you ask. No update is installed while a chip is
being read or written.

The installed package records the system it was built for in
`/usr/lib/t48-programmer/package-target`, and the update takes only the package
built for that system. When a release has no package for it, the About window
says so and opens the release page. A copy run from the source tree or
installed from the wheel has no such record and is also sent to the release
page.

To upgrade by hand, download the newer `.deb`, verify its checksum, and install
it with the same `apt install ./FILE.deb` command. A download that Check for
Application Updates could not install is kept in
`~/.cache/t48-programmer/updates` and can be installed the same way.

Images you have read or prepared are outside the package and are not replaced.

## Running from source

Install the toolkit from the distribution. It cannot be installed with pip in
any useful way, because PyGObject must match the system's GTK.

```sh
sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1
```

Build minipro from source. Ubuntu 24.04 does not package it.

```sh
sudo apt install build-essential pkg-config libusb-1.0-0-dev zlib1g-dev
git clone https://gitlab.com/DavidGriffith/minipro.git
cd minipro
git checkout 0.7.4
make
sudo make install
```

`make install` also installs minipro's udev rules. Replug the programmer
afterwards. Then, from a checkout of this repository:

```sh
./t48-programmer
```

Nothing is installed and nothing is written outside the folders you choose.

Where a distribution does package minipro, check what it ships with
`minipro --version`. Support for the T48 was experimental in 0.7 and much
improved in 0.7.3, so anything older than 0.7.3 is not worth using with a T48.

To use a particular binary without installing it, name it in the environment.
minipro reads its chip database from the folder compiled into it, or from
`MINIPRO_HOME` when that is set:

```sh
MINIPRO_HOME=~/src/minipro T48_PROGRAMMER_MINIPRO=~/src/minipro/minipro ./t48-programmer
```

## Permissions

If the start page says no programmer is connected, but `sudo minipro -k` in a
terminal finds it, the udev rules are missing or the programmer has not been
replugged since they were installed.

The rules tag the programmer for `uaccess`, which gives access to whoever is
logged in at the machine. On a system without systemd-logind they also assign
the device to the `plugdev` group, and your user must belong to it:

```sh
sudo usermod -aG plugdev "$USER"
```

Log out and in again for a new group to take effect.

## Building the package

```sh
sudo apt install build-essential pkg-config libusb-1.0-0-dev zlib1g-dev curl python3-pip
packaging/build-deb.sh
```

The script downloads the minipro release named in
`packaging/minipro-version.txt`, checks it against
`packaging/minipro-source.sha256`, compiles it for the prefix it will be
installed under, and writes the package to `dist/`. To move to a newer minipro,
change both files, update `VERSION` in `src/t48_programmer/simulator.py` to
match, and run the tests, which compare the two.

## Removing

```sh
sudo apt remove t48-programmer
```

Images you have read or prepared are yours and are not touched.
