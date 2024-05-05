{pkgs ? import <nixpkgs> {}}:
pkgs.mkShell {
  buildInputs = with pkgs; [
    python3Packages.discordpy
    python3Packages.pyyaml
    python3Packages.mcstatus
    python3Packages.pystray
    gobject-introspection
    gtk3
  ];
}
