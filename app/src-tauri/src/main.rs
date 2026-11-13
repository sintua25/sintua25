// Sembunyikan jendela konsol tambahan di Windows (rilis).
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    meja_vouching_lib::run()
}
