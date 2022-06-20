#
# This file is part of LiteX.
#
# Copyright (c) 2022 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

import os
import sys
import math
import subprocess
from shutil import which, copyfile

from migen.fhdl.structure import _Fragment

from litex.build.generic_platform import *
from litex.build import tools

# Timing Constraints (.sdc) ------------------------------------------------------------------------

def _build_sdc(clocks, vns, build_name):
    sdc = [
        f"create_clock -name {vns.get_name(clk)} -period {str(period)} [get_ports {{{vns.get_name(clk)}}}]"
        for clk, period in sorted(clocks.items(), key=lambda x: x[0].duid)
    ]

    with open(f"{build_name}.sdc", "w") as f:
        f.write("\n".join(sdc))

# Script -------------------------------------------------------------------------------------------

def _build_tcl(name, device, files, build_name, include_paths):
    tcl = [
        f"create_design {build_name}",
        f"target_device {device.upper()}",
        "add_include_path ./",
    ]


    tcl.extend(
        f"add_include_path {include_path}" for include_path in include_paths
    )

    # Add Sources.
    tcl.extend(f"add_design_file {f}" for f, typ, lib in files)
    # Set Top Module.
    tcl.append(f"set_top_module {build_name}")

    tcl.extend(
        (
            f"add_constraint_file {build_name}.sdc",
            "synth",
            "packing",
            "place",
            "route",
            "sta",
            "power",
            "bitstream",
        )
    )

    # Generate .tcl.
    with open("build.tcl", "w") as f:
        f.write("\n".join(tcl))

# OSFPGAToolchain -----------------------------------------------------------------------------------

class OSFPGAToolchain:
    attr_translate = {}

    def __init__(self, toolchain):
        self.toolchain = toolchain
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

        # Finalize design
        if not isinstance(fragment, _Fragment):
            fragment = fragment.get_fragment()
        platform.finalize(fragment)

        # Generate verilog
        v_output = platform.get_verilog(fragment, name=build_name, **kwargs)
        named_sc, named_pc = platform.resolve_signals(v_output.ns)
        v_file = f"{build_name}.v"
        v_output.write(v_file)
        platform.add_source(v_file)

        # Generate constraints file.
        # IOs.
        # TODO.

        # Timings (.sdc)
        _build_sdc(
            clocks     = self.clocks,
            vns        = v_output.ns,
            build_name = build_name,
        )

        # Generate build script (.tcl)
        script = _build_tcl(
            name          = platform.devicename,
            device        = platform.device,
            files         = platform.sources,
            build_name    = build_name,
            include_paths = platform.verilog_include_paths,
        )

        # Run
        if run:
            toolchain_sh = self.toolchain
            if which(toolchain_sh) is None:
                msg = f"Unable to find {toolchain_sh.upper()} toolchain, please:\n"
                msg += f"- Add {toolchain_sh.upper()} toolchain to your $PATH."
                raise OSError(msg)

            if subprocess.call([toolchain_sh, "--batch", "--script", "build.tcl"]) != 0:
                raise OSError(f"Error occured during {toolchain_sh.upper()}'s script execution.")

        os.chdir(cwd)

        return v_output.ns

    def add_period_constraint(self, platform, clk, period):
        clk.attr.add("keep")
        period = math.floor(period*1e3)/1e3 # round to lowest picosecond
        if clk in self.clocks and period != self.clocks[clk]:
            raise ValueError("Clock already constrained to {:.2f}ns, new constraint to {:.2f}ns"
                .format(self.clocks[clk], period))
        self.clocks[clk] = period
