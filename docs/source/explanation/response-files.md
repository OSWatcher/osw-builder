# Response files and unattended installs

To build an OS image without a human clicking through the installer, osw-builder feeds each OS an **answer file** (also called a response file) that pre-answers every installer prompt. Different OS families use entirely different formats, so osw-builder models them polymorphically.

## One concept, three formats

```{list-table}
:header-rows: 1

* - OS family
  - Answer file
  - Mechanism
* - Windows 10 / 11
  - `Autounattend.xml`
  - Windows Setup reads it automatically from the install media.
* - Windows XP
  - `WINNT.SIF`
  - The older text-INI unattended format.
* - Ubuntu (≤ 19.10)
  - `preseed.cfg`
  - Debian-installer preseeding.
* - Ubuntu (≥ 20.04)
  - autoinstall (cloud-init)
  - The modern Subiquity installer.
```

Each format answers the same kinds of questions — disk layout, locale, user accounts, network — but the syntax and delivery differ completely.

## Why a polymorphic interface

Rather than scatter `if windows: ... elif ubuntu: ...` throughout the build code, osw-builder defines a `ResponseFile` interface. Each OS type implements it with its own configuration logic and its own idea of *where* the file must be delivered (mounted into the build container, baked into the media, or served over the network). The build stage asks the response file two things — its contents and its mount path — and stays ignorant of the format.

This is what lets a single `windows.pkr.hcl` template build everything from Windows 7 to Windows 11: the per-version differences live in the answer file and the varfile, not in branching build code.

## How the answer file connects to inheritance

The answer file path is just another Packer variable (`answerfile_path`) carried in `build_config.vars`. Because `vars` merges through the {doc}`inheritance chain <image-inheritance>`, a whole branch can share one answer file, and a single release can override it by setting its own `answerfile_path`. The Ubuntu branch does exactly this at the 20.04 boundary, switching from the preseed answer file to the autoinstall directory while keeping everything else.

## The boot command wrinkle

Getting the installer to *load* the answer file often requires pressing specific keys at the boot menu — and those keystrokes changed across releases (`<F6>`, `<ESC><F6>`, GRUB-based entry for newer Ubuntu). These live in `build_config.vars` as `boot_command_prefix` / `boot_command`, overridden per release exactly where the installer UI changed. They are the most fiddly part of supporting a new OS version, because they depend on installer timing rather than configuration.
