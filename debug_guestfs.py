#!/usr/bin/env python3
"""Debug script for libguestfs mount operations with FUSE support."""

import logging
import sys
from pathlib import Path

from osw_builder.capture.guest_filesystem import LibguestFSMnt

# Configure logging to see what's happening
logging.basicConfig(
    level=logging.INFO,
    format="%(name)s - %(levelname)s - %(message)s",
)


def main():
    disk_path = Path("/home/wenzel/local/win11-25h2-26100.265.img")

    if not disk_path.exists():
        print(f"Error: Disk image not found at {disk_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Mounting disk: {disk_path}")
    print("This will provide a FUSE mount point for debugging...\n")

    try:
        mnt = LibguestFSMnt(disk_path, local=True, readonly=True)
        with mnt as mount_point:
            print(f"\n✓ Successfully mounted at: {mount_point}\n")
            print("Available in this shell:")
            print(f"  - mount_point = '{mount_point}'")
            print("  - mnt = LibguestFSMnt instance")
            print("  - mnt.gfs = guestfs.GuestFS instance\n")

            # Start IPython shell
            try:
                from IPython import embed

                embed(header="Debugging libguestfs mount. Type 'exit' or Ctrl+D to unmount and exit.")
            except ImportError:
                print("IPython not available, falling back to regular Python shell")
                print("Type 'exit()' or Ctrl+D to unmount and exit\n")
                import code

                code.interact(
                    banner="Debugging libguestfs mount (Python shell)", local={"mount_point": mount_point, "mnt": mnt}
                )

            print("\nUnmounting filesystem...")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.exit(1)

    print("✓ Cleanup completed successfully")


if __name__ == "__main__":
    main()
