// ConfiDoc — signature components entry point
import { init_trust_gauge } from "./trust-gauge.js";
import { init_scan_reveal } from "./scan-reveal.js";
import { init_privacy_lens } from "./privacy-lens.js";
import { init_command_palette } from "./command-palette.js";
import { init_drawer } from "./drawer.js";

export function initComponents() {
  init_trust_gauge();
  init_scan_reveal();
  init_privacy_lens();
  init_command_palette();
  init_drawer();
}
