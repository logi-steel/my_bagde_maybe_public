/*
  Mini e-ink badge case  -  parametric, OpenSCAD 2021.01+

  Two printed parts + a button cap, closed with 4x M2 screws from the BACK:
    bezel  front plate with the display window, a lip that centres it in the shell,
           panel stops and four screw columns that reach down to the back plate
    shell  back plate + walls: USB-C opening, button cage, lanyard lug, cradles
    cap    button plunger (prints standing up)

  Built around (README lists what is VERIFIED from datasheets and what is ASSUMED):
    2.13" e-paper panel 59.2 x 29.2 x 1.05, active area 48.55 x 23.71        (datasheet)
    Seeed XIAO ESP32-C3 21 x 17.8 (+ USB-C on a short edge)                  (Seeed wiki)
    LiPo pouch cell up to 6.5 x 21.5 x 42 ("602040" class)                   (nominal + margin)
    display driver board envelope 34 x 21 x 3.0                               (ASSUMPTION - measure)
    6x6 tact switch, 4.3 mm tall, lying on its side                           (common part)

  openscad -o shell.stl -D 'part="shell"' badge_case.scad
  part: assembly | exploded | bezel | shell | cap | fit_test | gauge | plate
        check_*  = interference tests, every one of them must come out EMPTY
*/

part = "assembly";
$fn = 36;

// ---------------------------------------------------------------- parts you buy (measure yours!)
panel_l = 59.2;  panel_w = 29.2;  panel_t = 1.05;     // 2.13" panel, landscape: length along X
aa_l = 48.55;    aa_w = 23.71;                         // active area
aa_far = 3.05;   // edge opposite the FPC -> first active pixel. Taken from the Waveshare drawing
                 // of the older 2.13" generation (same outline). VERIFY on your panel!
fpc_left = true; // FPC leaves the LEFT short edge (= firmware "rotation": 0); false = right

drv  = [34, 21, 3.0];     // display driver board envelope   (ASSUMPTION)
xiao = [21, 17.8, 5.0];   // XIAO ESP32-C3 incl. USB-C height (thickness from one source)
xiao_pcb_t = 1.0;         // XIAO PCB thickness (assumed; USB-C sits on top of it)
usb_h = 3.3;              // USB-C receptacle height
bat  = [42, 21.5, 6.5];   // LiPo envelope incl. protection board and wrap
sw   = [6.0, 6.0, 4.3];   // tact switch: width, height (lying on its side), length incl. plunger

// ---------------------------------------------------------------- design choices
wall = 2.0;  back_t = 2.0;  front_t = 1.4;
clr = 0.25;                 // panel clearance per side
lip_t = 1.2;  fit = 0.30;   // lip ring thickness, lip <-> cavity clearance per side
win_pad = 0.4;              // window is larger than the active area by this much per side
cr = 4.0;  cr_in = 0.8;     // outer / cavity corner radius
col_d = 4.6;  col_off = 2.5;   // screw columns: diameter, distance from the cavity walls
pilot_d = 1.7;  pilot_l = 9;   // M2 thread-forming screw pilot hole
scr_clear = 2.4;  scr_head = 4.0;
usb_w = 12.0;  usb_oh = 6.5;   // USB-C opening (clears the cable overmould)
btn_x = -24;                   // button on the bottom edge, above the narrow XIAO
btn_hole = 3.6;
cap_d = 3.2;  cap_flange_d = 6.0;  cap_flange_t = 0.8;
lug_r = 5.2;
magnets = false;               // optional 6x2 mm magnet pockets on the back
magnet_d = 6.2;  magnet_t = 2.2;

// ---------------------------------------------------------------- derived
bat_zone = bat[2] + 0.4;
drv_zone = drv[2] + 0.3;
pocket_d = panel_t + 0.2;
bay_h    = bat_zone + drv_zone + pocket_d;   // cavity depth below the shell rim
back_th  = magnets ? back_t + 1.0 : back_t;
z_floor  = back_th;
z_top    = z_floor + bay_h;                  // shell rim
H        = z_top + front_t;                  // total thickness

ci_x = 71;   ci_y = 33;                      // cavity inner size
ox = ci_x + 2 * wall;   oy = ci_y + 2 * wall;

fpc_sign = fpc_left ? -1 : 1;
aa_cx = -fpc_sign * (panel_l / 2 - aa_far - aa_l / 2);   // window centre vs panel centre

xiao_x = -ci_x / 2 + 0.4 + xiao[0] / 2;                    // XIAO at the left end (USB-C faces left)
bat_x  = -ci_x / 2 + 0.4 + xiao[0] + 2.0 + bat[0] / 2;
drv_x  = fpc_sign * (ci_x / 2 - 0.5 - drv[0] / 2);
col_x = ci_x / 2 - col_off;   col_y = ci_y / 2 - col_off;
usb_z = z_floor + xiao_pcb_t + usb_h / 2;                  // USB-C axis height
btn_z = z_floor + sw[1] / 2 + 0.3;
btn_pocket = cap_flange_t + 0.2 + sw[2] + 0.3;             // pocket length from the wall inward

// ---------------------------------------------------------------- sanity checks
assert(col_x - col_d / 2 >= panel_l / 2 + clr + 0.2, "screw columns collide with the panel ends - grow ci_x");
assert(col_y - col_d / 2 >= max(bat[1], drv[1], xiao[1]) / 2 + 0.3, "screw columns collide with battery/driver - grow ci_y");
assert(bat_x + bat[0] / 2 <= ci_x / 2 - 0.3, "battery + XIAO do not fit along X - grow ci_x");
assert(ci_y - 2 * fit - 2 * lip_t >= panel_w + 2 * clr - 0.5, "panel does not fit inside the lip ring");
assert(ci_y / 2 - btn_pocket - 0.8 >= bat[1] / 2 + 0.3 || btn_x < bat_x - bat[0] / 2 - 6, "button cage hits the battery");

// ---------------------------------------------------------------- helpers
module rbox(x, y, h, r) {
    hull() for (sx = [-1, 1], sy = [-1, 1])
        translate([sx * (x / 2 - r), sy * (y / 2 - r), 0]) cylinder(r = r, h = h);
}
module col_positions() {
    for (sx = [-1, 1], sy = [-1, 1]) translate([sx * col_x, sy * col_y, 0]) children();
}

// ---------------------------------------------------------------- the printed parts
module shell() {
    difference() {
        union() {
            rbox(ox, oy, z_top, cr);
            // lanyard lug on the top edge (badge hangs horizontally)
            hull() {
                translate([-6, oy / 2 - 2, 0]) cube([12, 2, 3]);
                translate([0, oy / 2 + lug_r - 1.6, 0]) cylinder(r = lug_r, h = 3);
            }
            // button cage block on the bottom edge, below the driver board layer
            translate([btn_x - (sw[0] + 3) / 2, -ci_y / 2 - 1, z_floor - 0.01])
                cube([sw[0] + 3, 1 + btn_pocket + 0.8, bat_zone]);
        }
        translate([0, 0, z_floor]) rbox(ci_x, ci_y, z_top, cr_in);                 // cavity
        // USB-C opening, axis aligned with the receptacle
        translate([-ci_x / 2 - wall - 1, -usb_w / 2, usb_z - usb_oh / 2]) cube([wall + 1.8, usb_w, usb_oh]);
        // button: pocket for flange + switch, hole for the plunger
        translate([btn_x - (sw[0] + 0.3) / 2, -ci_y / 2 - 0.01, btn_z - (sw[1] + 0.3) / 2])
            cube([sw[0] + 0.3, btn_pocket, sw[1] + 0.3]);
        translate([btn_x, -oy / 2 - 1, btn_z]) rotate([-90, 0, 0]) cylinder(d = btn_hole, h = wall + 2);
        col_positions() {                                                          // screws from the back
            translate([0, 0, -0.01]) cylinder(d = scr_clear, h = back_th + 0.02);
            translate([0, 0, -0.01]) cylinder(d1 = scr_head, d2 = scr_clear, h = 1.0);
        }
        translate([0, oy / 2 + lug_r - 1.6, -0.01]) cylinder(d = 3.6, h = 3.1);   // lug hole
        if (magnets) for (sx = [-1, 1]) translate([sx * 14, 0, -0.01]) cylinder(d = magnet_d, h = magnet_t);
    }
    // XIAO corner stops (low, parts drop in from above) and battery end stops
    for (sx = [-1, 1], sy = [-1, 1])
        translate([xiao_x + sx * (xiao[0] / 2 + 0.8) - 0.5, sy * (xiao[1] / 2 + 0.8) - 0.5, z_floor - 0.01])
            cube([1, 1, 2.2]);
    for (sx = [-1, 1])
        translate([bat_x + sx * (bat[0] / 2 + 0.8) - 0.6, -3, z_floor - 0.01]) cube([1.2, 6, 3.2]);
}

module panel_stops() {   // keep the panel from sliding along X; stay clear of the FPC tail
    far = -fpc_sign * (panel_l / 2 + clr + 0.5);
    near = fpc_sign * (panel_l / 2 + clr + 0.5);
    for (sy = [-1, 1]) {
        translate([far - 0.5, sy * 8 - 3, z_top - pocket_d]) cube([1, 6, pocket_d + 0.01]);
        translate([near - 0.5, sy * 10 - 2, z_top - pocket_d]) cube([1, 4, pocket_d + 0.01]);
    }
}

module bezel_body(columns = true) {
    difference() {
        union() {
            translate([0, 0, z_top]) rbox(ox, oy, front_t, cr);                        // front plate
            difference() {                                                             // lip ring
                translate([0, 0, z_top - pocket_d]) rbox(ci_x - 2 * fit, ci_y - 2 * fit, pocket_d + 0.01, cr_in);
                translate([0, 0, z_top - pocket_d - 0.01])
                    rbox(ci_x - 2 * fit - 2 * lip_t, ci_y - 2 * fit - 2 * lip_t, pocket_d + 0.1, 0.5);
            }
            panel_stops();
            if (columns) col_positions() translate([0, 0, z_floor]) cylinder(d = col_d, h = z_top - z_floor + 0.01);
        }
        if (columns) col_positions() translate([0, 0, z_floor - 0.01]) cylinder(d = pilot_d, h = pilot_l);
    }
}
module window() {
    translate([aa_cx - (aa_l + 2 * win_pad) / 2, -(aa_w + 2 * win_pad) / 2, z_top - 0.5])
        cube([aa_l + 2 * win_pad, aa_w + 2 * win_pad, front_t + 1]);
}
module bezel()    { difference() { bezel_body(true);  window(); } }
module fit_test() { difference() { bezel_body(false); window(); } }

module cap() {   // flange at z=0, shaft pointing +z; sits in the cage, shaft pokes out 0.8 mm
    cylinder(d = cap_flange_d, h = cap_flange_t);
    cylinder(d = cap_d, h = cap_flange_t + wall + 0.8);
}

// quick gauge: slots for the real XIAO, battery, driver board and switch -> test-fit your parts
module gauge() {
    t = 2.0;
    difference() {
        translate([-44, -30, 0]) cube([88, 60, t]);
        translate([-41, -26, -1]) cube([xiao[0] + 0.6, xiao[1] + 0.6, t + 2]);
        translate([-14, -26, -1]) cube([bat[0] + 0.6, bat[1] + 0.6, t + 2]);
        translate([-41, 0, -1]) cube([drv[0] + 0.6, drv[1] + 0.6, t + 2]);
        translate([-3, 6, -1]) cube([sw[0] + 0.3, sw[0] + 0.3, t + 2]);
        translate([14, 2, -1]) cube([panel_w - 14, panel_w - 14, t + 2]);   // thumb/pull hole
    }
}

// ---------------------------------------------------------------- stand-ins for the real parts
module d_panel()   { translate([-panel_l / 2, -panel_w / 2, z_top - panel_t]) cube([panel_l, panel_w, panel_t]); }
module d_driver()  { translate([drv_x - drv[0] / 2, -drv[1] / 2, z_floor + bat_zone]) cube([drv[0], drv[1], drv[2]]); }
module d_xiao()    { translate([xiao_x - xiao[0] / 2, -xiao[1] / 2, z_floor]) cube([xiao[0], xiao[1], xiao[2]]); }
module d_usb()     { translate([-ci_x / 2 - wall - 0.6, -4.5, usb_z - usb_h / 2]) cube([wall + 0.6 + 1.0, 9.0, usb_h]); }
module d_battery() { translate([bat_x - bat[0] / 2, -bat[1] / 2, z_floor]) cube([bat[0], bat[1], bat[2]]); }
module d_switch()  { translate([btn_x - sw[0] / 2, -ci_y / 2 + cap_flange_t + 0.2, btn_z - sw[1] / 2]) cube([sw[0], sw[2], sw[1]]); }
module d_cap()     { translate([btn_x, -ci_y / 2 + cap_flange_t, btn_z]) rotate([90, 0, 0]) cap(); }

// ---------------------------------------------------------------- views
module assembly() {
    color([0.86, 0.86, 0.88]) shell();
    color([0.16, 0.17, 0.2]) bezel();
    color([1, 1, 1]) d_panel();
    color([0.1, 0.35, 0.15]) d_driver();
    color([0.1, 0.55, 0.25]) d_xiao();
    color([0.75, 0.75, 0.8]) d_usb();
    color([0.2, 0.35, 0.85]) d_battery();
    color([0.85, 0.2, 0.2]) d_switch();
    color([0.97, 0.82, 0.2]) d_cap();
}
module exploded() {
    color([0.86, 0.86, 0.88]) shell();
    translate([0, 0, 38]) color([0.16, 0.17, 0.2]) bezel();
    translate([0, 0, 24]) { color([1, 1, 1]) d_panel(); color([0.1, 0.35, 0.15]) d_driver(); }
    translate([0, 0, 10]) { color([0.1, 0.55, 0.25]) d_xiao(); color([0.2, 0.35, 0.85]) d_battery(); }
    translate([0, -12, 0]) color([0.97, 0.82, 0.2]) d_cap();
}
module flipped_bezel(fit_only = false) {   // printed face down: window side on the bed
    translate([0, 0, z_top + front_t]) rotate([180, 0, 0]) if (fit_only) fit_test(); else bezel();
}
module plate() {
    shell();
    translate([0, oy + 10, 0]) flipped_bezel();
    translate([ox / 2 + 10, 0, 0]) cap();
}

// interference checks - each must be EMPTY
module check_shell() { intersection() { shell(); union() { d_panel(); d_driver(); d_xiao(); d_battery(); d_switch(); d_usb(); d_cap_free(); } } }
module d_cap_free() { // everything of the cap except the shaft that legitimately passes the wall hole
    translate([btn_x, -ci_y / 2 + cap_flange_t, btn_z]) rotate([90, 0, 0]) cylinder(d = cap_flange_d, h = cap_flange_t);
}
module check_bezel() { intersection() { bezel(); union() { d_panel(); d_driver(); d_xiao(); d_battery(); d_switch(); d_usb(); } } }
module check_fit()   { intersection() { shell(); bezel(); } }
module check_cap_wall() {   // plunger must clear the 3.6 mm hole, cage pocket must clear the flange
    intersection() { shell(); translate([btn_x, -ci_y / 2 + cap_flange_t, btn_z]) rotate([90, 0, 0]) cap(); }
}

if (part == "assembly") assembly();
else if (part == "exploded") exploded();
else if (part == "shell") shell();
else if (part == "bezel") flipped_bezel();
else if (part == "cap") cap();
else if (part == "fit_test") flipped_bezel(true);
else if (part == "gauge") gauge();
else if (part == "plate") plate();
else if (part == "check_shell") check_shell();
else if (part == "check_bezel") check_bezel();
else if (part == "check_fit") check_fit();
else if (part == "check_cap") check_cap_wall();
