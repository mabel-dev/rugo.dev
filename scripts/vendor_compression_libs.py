#!/usr/bin/env python3
"""
Vendor compression libraries for zero-dependency rugo builds
"""

import os
import shutil
import urllib.request
import tarfile
from pathlib import Path

def setup_vendor_directory():
    """Create vendor directory structure"""
    vendor_dir = Path("rugo/parquet/vendor")
    vendor_dir.mkdir(parents=True, exist_ok=True)
    return vendor_dir

def download_and_extract(url, filename, target_dir):
    """Download and extract a tarball"""
    print(f"Downloading {filename}...")
    urllib.request.urlretrieve(url, filename)
    
    print(f"Extracting {filename}...")
    with tarfile.open(filename, 'r:gz') as tar:
        tar.extractall()
    
    os.remove(filename)
    return target_dir

def vendor_snappy(vendor_dir):
    """Vendor Snappy compression library"""
    print("🔧 Vendoring Snappy...")
    
    # Download Snappy 1.1.10
    url = "https://github.com/google/snappy/archive/refs/tags/1.1.10.tar.gz"
    download_and_extract(url, "snappy.tar.gz", "snappy-1.1.10")
    
    # Move to vendor directory
    snappy_vendor = vendor_dir / "snappy"
    if snappy_vendor.exists():
        shutil.rmtree(snappy_vendor)
    shutil.move("snappy-1.1.10", snappy_vendor)
    
    # Keep only essential files for decompression
    essential_files = [
        "snappy.h",
        "snappy.cc", 
        "snappy-sinksource.h",
        "snappy-sinksource.cc",
        "snappy-stubs-internal.h", 
        "snappy-stubs-internal.cc",
        "snappy-stubs-public.h.in"
    ]
    
    # Clean up non-essential files
    for item in snappy_vendor.iterdir():
        if item.name not in essential_files and not item.name.startswith('.'):
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
    
    # Create minimal config.h
    config_h = snappy_vendor / "config.h"
    config_h.write_text("""#ifndef SNAPPY_CONFIG_H_
#define SNAPPY_CONFIG_H_

#define HAVE_STDINT_H 1
#define HAVE_STDDEF_H 1
#define SNAPPY_MAJOR 1
#define SNAPPY_MINOR 1  
#define SNAPPY_PATCHLEVEL 10

#endif
""")
    
    # Rename snappy-stubs-public.h.in to snappy-stubs-public.h
    in_file = snappy_vendor / "snappy-stubs-public.h.in"
    if in_file.exists():
        shutil.move(str(in_file), str(snappy_vendor / "snappy-stubs-public.h"))
    
    print(f"✅ Snappy vendored to {snappy_vendor}")

def vendor_zstd(vendor_dir):
    """Vendor Zstandard compression library"""
    print("🔧 Vendoring Zstd...")
    
    # Download Zstd 1.5.5
    url = "https://github.com/facebook/zstd/archive/refs/tags/v1.5.5.tar.gz"
    download_and_extract(url, "zstd.tar.gz", "zstd-1.5.5")
    
    # Move to vendor directory
    zstd_vendor = vendor_dir / "zstd"
    if zstd_vendor.exists():
        shutil.rmtree(zstd_vendor)
    shutil.move("zstd-1.5.5", zstd_vendor)
    
    # Keep only lib directory (common + decompress)
    lib_dir = zstd_vendor / "lib"
    if lib_dir.exists():
        # Create new clean structure
        new_zstd = vendor_dir / "zstd_new"
        new_zstd.mkdir()
        
        # Copy essential directories
        shutil.copytree(lib_dir / "common", new_zstd / "common")
        shutil.copytree(lib_dir / "decompress", new_zstd / "decompress") 
        
        # Copy main header
        main_header = lib_dir / "zstd.h"
        if main_header.exists():
            shutil.copy2(main_header, new_zstd / "zstd.h")
        
        # Replace old with new
        shutil.rmtree(zstd_vendor)
        shutil.move(new_zstd, zstd_vendor)
    
    print(f"✅ Zstd vendored to {zstd_vendor}")

def create_license_file(vendor_dir):
    """Create license attribution file"""
    license_text = """# Vendored Compression Libraries

This directory contains source code from third-party compression libraries,
included to provide zero-dependency builds of rugo.

## Snappy (Apache License 2.0)
- Version: 1.1.10
- Source: https://github.com/google/snappy
- License: Apache License 2.0

## Zstandard (BSD License)  
- Version: 1.5.5
- Source: https://github.com/facebook/zstd
- License: BSD License

See individual library directories for full license texts.

## Integration
These libraries are compiled directly into rugo for:
- Zero runtime dependencies
- Consistent cross-platform behavior  
- Simplified deployment
- Better performance through static linking
"""
    
    readme_path = vendor_dir / "README.md"
    readme_path.write_text(license_text)
    print(f"✅ License file created at {readme_path}")

def main():
    """Main vendoring process"""
    print("🚀 Starting vendoring process for rugo compression support...")
    
    # Change to repo root
    repo_root = Path(__file__).parent
    os.chdir(repo_root)
    
    # Setup vendor directory
    vendor_dir = setup_vendor_directory()
    
    # Vendor libraries
    vendor_snappy(vendor_dir)
    vendor_zstd(vendor_dir)
    
    # Create attribution
    create_license_file(vendor_dir)
    
    # Summary
    print("\n📊 Vendoring Summary:")
    for item in vendor_dir.iterdir():
        if item.is_dir():
            size = sum(f.stat().st_size for f in item.rglob('*') if f.is_file())
            print(f"  {item.name}: {size/1024:.1f} KB")
    
    print("\n✅ Vendoring complete! Next steps:")
    print("1. Update setup.py with vendored sources")
    print("2. Create compression.hpp/cpp files")  
    print("3. Integrate with decode.cpp")
    print("4. Test with compressed parquet files")

if __name__ == "__main__":
    main()