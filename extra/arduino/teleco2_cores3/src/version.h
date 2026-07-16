#pragma once

// Firmware version, monotonic integer — announced in the hello beacon as
// "hello <proto> <fw>". The player compares it against the embedded
// dist/teleco2_cores3-v<N>.bin and auto-flashes an off-version remote
// (host side: core/interfaces/teleco2.py).
//
// BUMP on every firmware change, then rebuild the dist artifact:
//   pio run -e cores3
//   python3 -m esptool --chip esp32s3 merge_bin -o dist/teleco2_cores3-v<N>.bin \
//     --flash_mode qio --flash_freq 80m --flash_size 16MB \
//     0x0 .pio/build/cores3/bootloader.bin 0x8000 .pio/build/cores3/partitions.bin \
//     0xe000 <framework>/tools/partitions/boot_app0.bin 0x10000 .pio/build/cores3/firmware.bin

#define FW_VERSION 3
