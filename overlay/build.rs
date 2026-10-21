const COMMON_CONTROLS_6: &str = "type='win32' name='Microsoft.Windows.Common-Controls' version='6.0.0.0' \
                                 processorArchitecture='*' publicKeyToken='6595b64144ccf1df' language='*'";
const PRODUCT: &str = "Explorers Companion";

fn resource_script(manifest_dir: &str, version: &str) -> String {
    let icon = format!("{manifest_dir}/assets/ed-overlay.ico").replace('\\', "/");
    let numeric = version.split('.').chain(std::iter::repeat("0")).take(4).collect::<Vec<_>>().join(",");
    format!(
        r#"1 ICON "{icon}"
1 VERSIONINFO
FILEVERSION {numeric}
PRODUCTVERSION {numeric}
FILEOS 0x40004
FILETYPE 0x1
BEGIN
  BLOCK "StringFileInfo"
  BEGIN
    BLOCK "040904b0"
    BEGIN
      VALUE "FileDescription", "{PRODUCT}"
      VALUE "ProductName", "{PRODUCT}"
      VALUE "FileVersion", "{version}"
      VALUE "ProductVersion", "{version}"
      VALUE "InternalName", "ed-overlay"
      VALUE "OriginalFilename", "ed-overlay.exe"
    END
  END
  BLOCK "VarFileInfo"
  BEGIN
    VALUE "Translation", 0x409, 1200
  END
END
"#
    )
}

fn main() {
    println!("cargo:rerun-if-changed=build.rs");
    println!("cargo:rerun-if-changed=assets/ed-overlay.ico");
    if std::env::var("CARGO_CFG_TARGET_ENV").as_deref() == Ok("msvc") {
        println!("cargo:rustc-link-arg-bins=/MANIFEST:EMBED");
        println!("cargo:rustc-link-arg-bins=/MANIFESTDEPENDENCY:{COMMON_CONTROLS_6}");
    }
    let out = std::path::PathBuf::from(std::env::var("OUT_DIR").unwrap()).join("ed-overlay.rc");
    let manifest_dir = std::env::var("CARGO_MANIFEST_DIR").unwrap();
    let version = std::env::var("CARGO_PKG_VERSION").unwrap();
    std::fs::write(&out, resource_script(&manifest_dir, &version)).unwrap();
    embed_resource::compile(&out, embed_resource::NONE).manifest_optional().unwrap();
}
