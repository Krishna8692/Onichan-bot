{pkgs}: {
  deps = [
    pkgs.xorg.libxshmfence
    pkgs.xorg.libxcb
    pkgs.libgbm
    pkgs.cairo
    pkgs.pango
    pkgs.glib
    pkgs.dbus
    pkgs.alsa-lib
    pkgs.expat
    pkgs.mesa
    pkgs.xorg.libXrandr
    pkgs.xorg.libXfixes
    pkgs.xorg.libXext
    pkgs.xorg.libXdamage
    pkgs.xorg.libXcomposite
    pkgs.xorg.libX11
    pkgs.libxkbcommon
    pkgs.libdrm
    pkgs.cups
    pkgs.at-spi2-atk
    pkgs.atk
    pkgs.nspr
    pkgs.nss
    pkgs.unzip
  ];
}
