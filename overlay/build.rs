const COMMON_CONTROLS_6: &str = "type='win32' name='Microsoft.Windows.Common-Controls' version='6.0.0.0' \
                                 processorArchitecture='*' publicKeyToken='6595b64144ccf1df' language='*'";

fn main() {
    println!("cargo:rerun-if-changed=build.rs");
    println!("cargo:rerun-if-changed=assets/ed-overlay.rc");
    println!("cargo:rerun-if-changed=assets/ed-overlay.ico");
    if std::env::var("CARGO_CFG_TARGET_ENV").as_deref() == Ok("msvc") {
        println!("cargo:rustc-link-arg-bins=/MANIFEST:EMBED");
        println!("cargo:rustc-link-arg-bins=/MANIFESTDEPENDENCY:{COMMON_CONTROLS_6}");
    }
    embed_resource::compile("assets/ed-overlay.rc", embed_resource::NONE).manifest_optional().unwrap();
}
