#
# This file is part of LiteX.
#
# Copyright (c) 2021 Miodrag Milanovic <mmicko@gmail.com>
# Copyright (c) 2015-2021 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

import os
import math
import subprocess
import datetime
from shutil import which

from migen.fhdl.structure import _Fragment

from litex.build.generic_platform import *
from litex.build import tools

# Constraints (.adc and .sdc) ----------------------------------------------------------------------

def _build_adc(named_sc, named_pc):
    adc = []

    flat_sc = []
    for name, pins, other, resource in named_sc:
        if len(pins) > 1:
            flat_sc.extend((f"{name}[{i}]", p, other) for i, p in enumerate(pins))
        else:
            flat_sc.append((name, pins[0], other))

    for name, pin, other in flat_sc:
        line = f"set_pin_assignment {{{name}}} {{ LOCATION = {pin}; "
        for c in other:
            if isinstance(c, IOStandard):
                line += f" IOSTANDARD = {c.name}; "
        line += "}}"
        adc.append(line)

    if named_pc:
        adc.extend(named_pc)

    with open("top.adc", "w") as f:
        f.write("\n".join(adc))

def _build_sdc(clocks, vns):
    sdc = [
        f"create_clock -name {vns.get_name(clk)} -period {str(period)} [get_ports {{{vns.get_name(clk)}}}]"
        for clk, period in sorted(clocks.items(), key=lambda x: x[0].duid)
    ]

    with open("top.sdc", "w") as f:
        f.write("\n".join(sdc))

# Script -------------------------------------------------------------------------------------------

def _build_al(name, family, device, files):
    xml = []

    date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    xml.extend(
        (
            f"<?xml version=\"1.0\" encoding=\"UTF-8\"?>",
            f"<Project Version=\"1\" Path=\"...\">",
            f"    <Project_Created_Time>{date}</Project_Created_Time>",
            "    <TD_Version>5.0.28716</TD_Version>",
            "    <UCode>00000000</UCode>",
            f"    <Name>{name}</Name>",
            "    <HardWare>",
            f"        <Family>{family}</Family>",
            f"        <Device>{device}</Device>",
            "    </HardWare>",
            "    <Source_Files>",
            "        <Verilog>",
        )
    )

    # Add Sources.
    for f, typ, lib in files:
        xml.extend(
            (
                f"            <File Path=\"{f}\">",
                "                <FileInfo>",
                f"                    <Attr Name=\"UsedInSyn\" Val=\"true\"/>",
                f"                    <Attr Name=\"UsedInP&R\" Val=\"true\"/>",
                f"                    <Attr Name=\"BelongTo\" Val=\"design_1\"/>",
                f"                    <Attr Name=\"CompileOrder\" Val=\"1\"/>",
                "               </FileInfo>",
                "            </File>",
            )
        )

    xml.extend(
        (
            "        </Verilog>",
            "        <ADC_FILE>",
            f"            <File Path=\"top.adc\">",
            "                <FileInfo>",
            f"                    <Attr Name=\"UsedInSyn\" Val=\"true\"/>",
            f"                    <Attr Name=\"UsedInP&R\" Val=\"true\"/>",
            f"                    <Attr Name=\"BelongTo\" Val=\"constrain_1\"/>",
            f"                    <Attr Name=\"CompileOrder\" Val=\"1\"/>",
            "               </FileInfo>",
            "            </File>",
            "        </ADC_FILE>",
            "        <SDC_FILE>",
            f"            <File Path=\"top.sdc\">",
            "                <FileInfo>",
            f"                    <Attr Name=\"UsedInSyn\" Val=\"true\"/>",
            f"                    <Attr Name=\"UsedInP&R\" Val=\"true\"/>",
            f"                    <Attr Name=\"BelongTo\" Val=\"constrain_1\"/>",
            f"                    <Attr Name=\"CompileOrder\" Val=\"2\"/>",
            "               </FileInfo>",
            "            </File>",
            "        </SDC_FILE>",
            "    </Source_Files>",
            "   <FileSets>",
            f"        <FileSet Name=\"constrain_1\" Type=\"ConstrainFiles\">",
            "        </FileSet>",
            f"        <FileSet Name=\"design_1\" Type=\"DesignFiles\">",
            "        </FileSet>",
            "    </FileSets>",
            "    <TOP_MODULE>",
            "        <LABEL></LABEL>",
            f"        <MODULE>{name}</MODULE>",
            "        <CREATEINDEX>auto</CREATEINDEX>",
            "    </TOP_MODULE>",
            "    <Property>",
            "    </Property>",
            "    <Device_Settings>",
            "    </Device_Settings>",
            "    <Configurations>",
            "    </Configurations>",
            "    <Project_Settings>",
            f"        <Step_Last_Change>{date}</Step_Last_Change>",
            "        <Current_Step>0</Current_Step>",
            f"        <Step_Status>true</Step_Status>",
            f"    </Project_Settings>",
            f"</Project>",
        )
    )

    # Generate .al.
    with open(f"{name}.al", "w") as f:
        f.write("\n".join(xml))

def _build_tcl(name, architecture, package):
    tcl = [
        f"import_device {architecture}.db -package {package}",
        f"open_project {name}.al",
        f"elaborate -top {name}",
        "read_adc top.adc",
        "optimize_rtl",
        "read_sdc top.sdc",
        "optimize_gate",
        "legalize_phy_inst",
        "place",
        "route",
        f"bitgen -bit \"{name}.bit\" -version 0X00 -g ucode:000000000000000000000000",
    ]


    # Generate .tcl.
    with open("run.tcl", "w") as f:
        f.write("\n".join(tcl))


# TangDinastyToolchain -----------------------------------------------------------------------------------

def parse_device(device):
    
    devices = {
        "EG4S20BG256" :[ "eagle_s20", "EG4", "BG256" ],
    }

    if device not in devices.keys():
        raise ValueError(f"Invalid device {device}")

    (architecture, family, package) = devices[device]
    return (architecture, family, package)

class TangDinastyToolchain:
    attr_translate = {}

    def __init__(self):
        self.clocks = {}

    def build(self, platform, fragment,
        build_dir  = "build",
        build_name = "top",
        run        = True,
        **kwargs):

        # Create build directory.
        cwd = os.getcwd()
        os.makedirs(build_dir, exist_ok=True)
        os.chdir(build_dir)

        # Finalize design.
        if not isinstance(fragment, _Fragment):
            fragment = fragment.get_fragment()
        platform.finalize(fragment)

        # Generate verilog.
        v_output = platform.get_verilog(fragment, name=build_name, **kwargs)
        named_sc, named_pc = platform.resolve_signals(v_output.ns)
        v_file = f"{build_name}.v"
        v_output.write(v_file)
        platform.add_source(v_file)

        # Generate constraints file.
        # IOs (.adc).
        _build_adc(
            named_sc = named_sc,
            named_pc = named_pc
        )

        # Timings (.sdc).
        _build_sdc(
            clocks  = self.clocks,
            vns     = v_output.ns
        )

        architecture, family, package = parse_device(platform.device)

        # Generate project file (.al).
        al = _build_al(          
            name         = build_name,
            family       = family,
            device       = platform.device,
            files        = platform.sources)

        # Generate build script (.tcl).
        script = _build_tcl(          
            name         = build_name,
            architecture = architecture,
            package      = package)

        # Run.
        if run:
            if which("td") is None:
                msg = (
                    "Unable to find Tang Dinasty toolchain, please:\n"
                    + "- Add  Tang Dinasty toolchain to your $PATH."
                )

                raise OSError(msg)

            if subprocess.call(["td", "run.tcl"]) != 0:
                raise OSError("Error occured during Tang Dinasty's script execution.")

        os.chdir(cwd)

        return v_output.ns

    def add_period_constraint(self, platform, clk, period):
        clk.attr.add("keep")
        period = math.floor(period*1e3)/1e3 # round to lowest picosecond
        if clk in self.clocks and period != self.clocks[clk]:
            raise ValueError("Clock already constrained to {:.2f}ns, new constraint to {:.2f}ns"
                .format(self.clocks[clk], period))
        self.clocks[clk] = period
