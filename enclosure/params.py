"""Every number the enclosure is built from.

Board geometry is NOT here: it is read from the KiCad files (see board.py).
Part dimensions that KiCad has no 3D model for come from datasheets, listed in SOURCES.
"""
import math

# --- print / fit parameters (free to change) ---------------------------------
WALL = 2.0            # side wall
FLOOR = 2.4           # base floor (leaves 1.7 mm under a 6.7 mm insert hole)
PLATE = 2.0           # lid top plate
CLR_BOARD = 0.5       # board edge to inner wall
CLR_PANEL = 0.3       # e-paper glass to its locating ribs
RIB = 1.7             # locating / battery ribs
BOSS_OD = 7.4         # every boss: insert hole 4.0 -> wall 1.7; clearance hole 3.4 -> wall 2.0
CLR_HOLE_M3 = 3.4     # ISO 273 medium fit
MOUNT = "screw"       # only screw + heat-set insert is implemented

# --- z levels (board bottom = 0, same frame as the KiCad STEP) ----------------
Z_FLOOR_BOT = -8.4
Z_FLOOR_TOP = Z_FLOOR_BOT + FLOOR      # -6.0, battery sits here
Z_SPLIT = -2.0                         # base walls end / lid walls start
Z_CORNER_JOINT = 2.0                   # base corner columns end / lid corner columns start

# --- e-paper panel GDEY029T94 (datasheet p.7 mechanical drawing) --------------
PANEL_W = 36.70       # short side, FPC side
PANEL_L = 79.00
PANEL_T = 1.20
VA_W, VA_L = 29.856, 67.696           # viewing area
VA_FROM_FAR_END = 2.60                # VA edge to the panel end opposite the FPC
VA_FROM_SIDE = 3.42                   # VA edge to the long side that is "bottom" on the drawing
FPC_W = 12.50
FPC_T = 0.30
FPC_LEN = 14.40                       # glass edge to tail end
FPC_TOP_OFFSET = 10.42                # glass "top" edge (drawing) to FPC tail edge
FPC_STIFFENER = 3.66
# assumptions (no datasheet number): see README "Not certain"
FPC_EXIT_ABOVE_PANEL_BOTTOM = 0.30    # FPC leaves the glass 0.3 mm above its underside
J4_SLOT_Z_ABOVE_BOARD = 0.90          # FPC enters J4 0.9 mm above the board top
FPC_LOOP_GAP = 1.50                   # straight FPC run in front of the J4 mouth (loop apex to J4 front face)

# --- parts with no KiCad 3D model: height from datasheets ---------------------
H_USBC = 3.16         # HRO TYPE-C-31-M-12 body height
H_TACT = 1.50         # XKB TS-1187A-B-A-B total height
TACT_BODY = 5.10
H_JST_PH_SIDE = 5.50  # S2B-PH-SM4-TB side-entry header height
H_FPC_CONN = 2.00     # Jushuo AFC07-S24FCA-00 height above board
# mating plugs
USB_SHELL = (8.40, 2.60)        # envelope around the largest plug shell 8.34 x 2.56 (KC opening figure, dekra source in SOURCES)
USB_OVERMOLD = (12.85, 7.00)    # USB Type-C spec max after ECN 2023 (pre-ECN 12.35 x 6.5)
PHR2 = dict(width=5.8, length=6.85, height=4.5)
SHR04 = dict(width=7.0, length=5.0, height=2.8)   # width with protrusions

# --- fasteners -----------------------------------------------------------------
INSERT_HOLE_D = 4.0     # ruthex RX-M3x5.7 recommended hole
INSERT_HOLE_DEPTH = 6.7 # insert length 5.7 + 1.0
INSERT_LEN = 5.7
INSERT_MIN_WALL = 1.6
SCREW_HEAD_D = 5.6      # ISO 7045 M3 pan head dk max
SCREW_HEAD_K = 2.4      # ISO 7045 M3 pan head k max

# --- battery (assumption: 1000 mAh "503450" cell, naming convention 5.0 x 34 x 50) --
BATT = (50.0, 34.0, 5.0)
BATT_CLR = 0.5
LIP_T, LIP_CLR, LIP_H = 1.7, 0.2, 2.0   # lid locating lip inside the base wall
PANEL_TOP_LAYER = (74.50, 33.66, 0.80, 1.52)  # PS length, width, from far end, from VA side (datasheet p.7)
PANEL_TFT_T = 0.60      # assumption: split of the 1.2 mm stack
BONDING_STRIP = 4.5     # FPC-side strip kept clear of tape and lid (IC bonding area)
BONDING_RELIEF = 0.3

# openings
USB_POCKET_CLR = 0.30   # per side around the 12.85 x 7.0 overmold; the pocket goes through the wall
USB_RECEPTACLE_DEPTH = 6.20   # mouth to mating datum (USB Type-C R2.0 via the source in SOURCES)
USB_OVERMOLD_DATUM_MAX = 6.50 # USB-IF Locking Connector Spec rev 1.0: overmold face to mating datum, max
USB_MOUTH_GAP_MAX = 0.35      # plug shell 6.65 - receptacle 6.20 - 0.10 tol: allowed overmold stand-off
QWIIC_OPEN_CLR = 0.30
RESET_PIN_D = 2.2       # paper-clip / pin hole over the RESET button
RESET_TUBE_BOTTOM_GAP = 0.9
LED_PIPE_D = 2.0        # 2 mm PMMA rod as light pipe
LED_BORE_D = 2.1
LED_PIPE_GAP = 0.5      # rod end above the LED
WINDOW_CHAMFER = 0.4      # plate 2.0 - 0.4 = 1.6 left at the lip

SOURCES = {
    "GDEY029T94": "Good Display GDEY029T94 datasheet p.7 (mechanical drawing), https://www.laskakit.cz/user/related_files/gdey029t94.pdf",
    "HRO TYPE-C-31-M-12": "8.94 x 7.35 x 3.16 mm, https://en.krhro.com/Product-Details/726.html",
    "XKB TS-1187A-B-A-B": "5.1 x 5.1, H 1.5, actuator 2.0, XKB drawing p.1, https://xonstorage.z8.web.core.windows.net/pdf/xkb_ts1187abib_apr22_xonlink.pdf",
    "JST S2B-PH-SM4-TB": "side entry: height 5.5, depth 6 (+2.6 leads), JST PH catalogue p.4, https://www.jst-mfg.com/product/pdf/eng/ePH.pdf",
    "JST PHR-2": "B 5.8, length 6.85, height 4.5, JST PH catalogue p.3",
    "JST SHR-04V-S": "B 5.0 (7.0 with protrusions), height 2.8, length 5, JST SH catalogue p.2, https://www.jst-mfg.com/product/pdf/eng/eSH.pdf",
    "Jushuo AFC07-S24FCA-00": "height 2.00 (distributor page, tier B), https://www.xonelec.com/mpn/jushuo/afc07s24fca00",
    "ruthex RX-M3x5.7": "hole 4.0, L 5.7, min wall 1.6, https://www.igo3d.com/mediafiles/Sonstiges/Ruthex/ruthex_Datenblatt_RX-Serie.pdf; depth L+1 = 6.7 (tier C rule, https://machinistcalcs.com/guides/heat-set-insert-holes/)",
    "USB-C mating": "receptacle depth 6.20, plug shell 6.65+-0.10 (https://electronics.stackexchange.com/questions/521884); overmold face <= 6.5 mm from mating datum (USB Type-C Locking Connector Specification rev 1.0, https://www.usb.org/sites/default/files/documents/usb_type-c_locking_connector_specification_rev_1_0_20160309_0.pdf)",
    "USB-C plug shell max 8.34 x 2.56": "enclosure opening figure, https://dekraprod-media.e-spirit.cloud/d429af9d-aa2c-4b43-a4b8-b9b1ae69df3e/media/dekra-pr (tier B)",
    "Jushuo AFC07-S24FCA-00 contact": "Bottom Contact, Slide Lock (LCSC C262567 part page, tier B), https://lcsc.com/product-detail/FFC-FPC-Flat-Flexible-Connector-Assemblies_JUSHUO-AFC07-S24FCA-00_C262567.html",
    "USB-C overmold": "12.85 x 7.0 max after USB Type-C ECN 2023 (tier B, https://www.allion.com.tw/news-center/cabc_usb_update/)",
    "ISO 7045 M3": "pan head dk 5.6, k 2.4 (max)",
    "ISO 273": "M3 clearance hole, medium 3.4",
}


def fpc_loop(panel_bottom_z, board_top_z, j4_front_y, j4_back_y):
    """FPC tail path: out of the glass, 180 deg loop, back into J4.

    Returns (glass_edge_y, loop_y, r, z_exit, z_slot). y grows toward the panel.
    Tail length is fixed by the datasheet; the glass edge position follows from it.
    """
    z_exit = panel_bottom_z + FPC_EXIT_ABOVE_PANEL_BOTTOM
    z_slot = board_top_z + J4_SLOT_Z_ABOVE_BOARD
    r = (z_exit - z_slot) / 2
    loop_y = j4_front_y - FPC_LOOP_GAP
    end_y = j4_front_y + FPC_STIFFENER          # tail end inside the connector
    glass_y = loop_y + FPC_LEN - math.pi * r - (end_y - loop_y)
    return glass_y, loop_y, r, z_exit, z_slot, end_y
