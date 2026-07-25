# Blender Asset Factory

Canonical local production root for optimized PS1-era Three.js assets.

## Canonical directories

- Projects: `G:\DevWork\GameDev\BlenderAssetFactory\projects`
- Generated assets: `G:\DevWork\GameDev\BlenderAssetFactory\assets`
- Specifications: `G:\DevWork\GameDev\BlenderAssetFactory\specs`
- Generators: `G:\DevWork\GameDev\BlenderAssetFactory\scripts`
- Standalone renders: `G:\DevWork\GameDev\BlenderAssetFactory\renders`

New generators and project files belong beneath this root. Specifications control their output directory and must target the `assets` directory unless a project requires a dedicated subfolder.

## Generate the reference asset

```powershell
& 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' `
  --background --factory-startup `
  --python 'G:\DevWork\GameDev\BlenderAssetFactory\scripts\generate_asset.py' `
  -- --spec 'G:\DevWork\GameDev\BlenderAssetFactory\specs\ps1_crate.json'
```

Blender MCP is restricted to this canonical directory and listens only on `127.0.0.1:9876`.
