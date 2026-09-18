from __future__ import annotations

import unittest

from t48_programmer.gtk_environment import scrub_snap_environment


class ScrubSnapEnvironmentTests(unittest.TestCase):
    def test_removes_toolkit_paths_that_point_into_a_snap(self) -> None:
        environment = {
            "GTK_PATH": "/snap/code/258/usr/lib/x86_64-linux-gnu/gtk-3.0",
            "GDK_PIXBUF_MODULE_FILE": "/home/me/snap/code/common/.cache/loaders.cache",
            "HOME": "/home/me",
        }

        scrub_snap_environment(environment)

        self.assertEqual(environment, {"HOME": "/home/me"})

    def test_keeps_a_toolkit_path_the_user_set_themselves(self) -> None:
        environment = {
            "GTK_PATH": "/opt/gtk/lib",
            "GSETTINGS_SCHEMA_DIR": "/usr/share/x",
        }

        scrub_snap_environment(environment)

        self.assertEqual(
            environment,
            {"GTK_PATH": "/opt/gtk/lib", "GSETTINGS_SCHEMA_DIR": "/usr/share/x"},
        )

    def test_keeps_the_rest_of_the_library_path(self) -> None:
        environment = {"LD_LIBRARY_PATH": "/snap/core20/lib:/opt/lib::/snap/x/lib"}

        scrub_snap_environment(environment)

        self.assertEqual(environment["LD_LIBRARY_PATH"], "/opt/lib")


if __name__ == "__main__":
    unittest.main()
