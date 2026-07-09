# The image inheritance model

The image catalogue could have been a flat list where every OS repeats its full build configuration. Instead it uses **chronological inheritance**: images are grouped into branches, and each image inherits the accumulated configuration of every image before it. This page explains why, and exactly how resolution works.

## The problem it solves

Windows 10 shipped in roughly twenty feature updates between 2015 and 2022. Almost all of them build identically — same Packer template, same answer file, same product key. Only a handful differ (Windows 11 needs UEFI; some Ubuntu releases need a mirror flag flipped). Repeating the full config for every entry would be enormous and error-prone: fix a bug in the template reference and you would have to fix it in twenty places.

Inheritance lets the *first* image in a branch establish the baseline, and every later image express only its **delta**.

## How a branch is read

A branch is an **ordered** list. Resolution walks it from top to bottom, accumulating configuration, and stops at the target image. Consider the `ubuntu-server` branch:

```yaml
branches:
  ubuntu-server:
    - name: *ubuntu_6_10
      build_config:
        template: *ubuntu_template
        varfiles: ["ubuntu.pkrvars/preseed.pkrvars.hcl"]
        vars:
          answerfile_path: "./answer_files/ubuntu/preseed.cfg"
      runtime_config:
        idle: false
        search_updates: false
    - *ubuntu_7_04          # inherits everything above
    - name: *ubuntu_7_10
      build_config:
        vars:
          preseed_disk_device: "/dev/sda"   # delta only
```

Resolving `ubuntu-7.10` walks `6.10` (sets the baseline), `7.04` (no change), then `7.10` (adds one var) and stops. The result is the 6.10 baseline plus `preseed_disk_device: /dev/sda`.

## The merge rules

Not every field merges the same way. The distinction matters:

```{list-table}
:header-rows: 1

* - Field
  - Strategy
* - `template`
  - **Replace** — a later value wins.
* - `varfiles`
  - **Replace** — the whole list is swapped, not extended.
* - `vars`
  - **Merge** — individual keys are updated; unspecified keys are kept.
* - other `build_config` keys
  - **Replace** — `network`, `key`, `image_name`, etc.
* - `runtime_config`
  - **Merge** — keys are updated individually.
```

The most common mistake is expecting `varfiles` to extend. It does not — if you set `varfiles` in a later entry, you replace the inherited list entirely. This is deliberate: the autoinstall-era Ubuntu releases (20.04+) switch varfiles wholesale rather than adding to the preseed set.

## "Sticky" disabling in runtime_config

There is one extra rule that lives in the CLI rather than the resolver: a `runtime_config` value of `false` cannot be overridden back to `true` by a command-line flag. If an image declares `search_updates: false` because that OS genuinely cannot search for updates, `--search-updates=true` is ignored. This keeps known-broken phases off, even when a user passes a blanket flag.

## Why "exactly one branch"

An image must appear in exactly one branch. If it appeared in two, resolution would be ambiguous — which chain of ancestors applies? The resolver raises an error rather than guess. In practice the two branches (`windows`, `ubuntu-server`) are cleanly separated by OS family, so this is never a real constraint, only a guardrail.

## The payoff

Adding a new OS release is usually a two-line change: an anchor in `images:` and an alias in the branch. Everything else is inherited. See {doc}`../how-to/add-new-image` for the procedure.
