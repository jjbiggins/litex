#
# This file is part of LiteX.
#
# Copyright (c) 2021 Franck Jullien <franck.jullien@collshade.fr>
# Copyright (c) 2021 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

from migen import *
from migen.genlib.resetsync import AsyncResetSynchronizer

from litex.build.generic_platform import *
from litex.soc.cores.clock.common import *

class Open(Signal): pass

# Efinix / TRIONPLL ----------------------------------------------------------------------------------

class EFINIXPLL(Module):
    nclkouts_max = 3
    def __init__(self, platform, n=0, version="V1_V2"):
        self.logger = logging.getLogger("EFINIXPLL")

        if version == "V1_V2":
            self.type = "TRIONPLL"
        elif version == "V3":
            self.type = "TITANIUMPLL"
        else:
            self.logger.error(f"PLL version {version} not supported")
            quit()

        self.logger.info(f'Creating {colorer(self.type, color="green")}')
        self.platform   = platform
        self.nclkouts   = 0
        self.reset      = Signal()
        self.locked     = Signal()
        self.name       = f"pll{n}"

        # Create PLL block.
        block = {
            "type": "PLL",
            "name": self.name,
            "clk_out": [],
            "locked": f"{self.name}_locked",
            "rstn": f"{self.name}_rstn",
            "version": version,
        }

        self.platform.toolchain.ifacewriter.blocks.append(block)

        # Connect PLL's rstn/locked.
        self.comb += self.platform.add_iface_io(f"{self.name}_rstn").eq(~self.reset)
        self.comb += self.locked.eq(self.platform.add_iface_io(f"{self.name}_locked"))

    def register_clkin(self, clkin, freq, name=""):
        block = self.platform.toolchain.ifacewriter.get_block(self.name)

        block["input_clock_name"] = self.platform.get_pin_name(clkin)

        # If clkin has a pin number, PLL clock input is EXTERNAL
        if self.platform.get_pin_location(clkin):
            pad_name = self.platform.get_pin_location(clkin)[0]
            # PLL v1 needs pin name
            pin_name = self.platform.parser.get_pad_name_from_pin(pad_name)
            if pin_name.count("_") == 2:
                pin_name = pin_name.rsplit("_", 1)[0]
            self.platform.toolchain.excluded_ios.append(clkin)

            #tpl = "create_clock -name {clk} -period {period} [get_ports {{{clk}}}]"
            #sdc = self.platform.toolchain.additional_sdc_commands
            #sdc.append(tpl.format(clk=block["input_clock_name"], period=1/freq))

            try:
                (pll_res, clock_no) = self.platform.parser.get_pll_inst_from_pin(pad_name)
            except:
                self.logger.error(f"Cannot find a pll with {pad_name} as input")
                quit()

            block["input_clock"]     = "EXTERNAL"
            block["input_clock_pad"] = pin_name
            block["resource"]        = pll_res
            block["clock_no"]        = clock_no
            self.logger.info(
                f'Clock source: {block["input_clock"]}, using EXT_CLK{clock_no}'
            )

            self.platform.get_pll_resource(pll_res)
        else:
            block["input_clock"]  = "INTERNAL"
            block["resource"]     = self.platform.get_free_pll_resource()
            block["input_signal"] = name
            self.logger.info(f'Clock source: {block["input_clock"]}')

        self.logger.info("PLL used     : " + colorer(str(self.platform.pll_used), "cyan"))
        self.logger.info("PLL available: " + colorer(str(self.platform.pll_available), "cyan"))

        block["input_freq"] = freq

        self.logger.info(f'Use {colorer(block["resource"], "green")}')

    def create_clkout(self, cd, freq, phase=0, margin=0, name="", with_reset=True):
        assert self.nclkouts < self.nclkouts_max

        clk_out_name = f"{self.name}_clkout{self.nclkouts}" if name == "" else name
        self.platform.toolchain.additional_sdc_commands.append(f"create_clock -period {1e9/freq} {clk_out_name}")

        if cd is not None:
            self.platform.add_extension([(clk_out_name, 0, Pins(1))])
            self.comb += cd.clk.eq(self.platform.request(clk_out_name))
            if with_reset:
                self.specials += AsyncResetSynchronizer(cd, ~self.locked)
            self.platform.toolchain.excluded_ios.append(clk_out_name)

        create_clkout_log(self.logger, clk_out_name, freq, margin, self.nclkouts)

        self.nclkouts += 1

        block = self.platform.toolchain.ifacewriter.get_block(self.name)
        block["clk_out"].append([clk_out_name, freq, phase, margin])

    def extra(self, extra):
        block = self.platform.toolchain.ifacewriter.get_block(self.name)
        block["extra"] = extra

    def compute_config(self):
        pass

    def set_configuration(self):
        pass

    def do_finalize(self):
        pass

# Efinix / TITANIUMPLL -----------------------------------------------------------------------------

class TITANIUMPLL(EFINIXPLL):
    nclkouts_max = 5
    def __init__(self, platform, n=0):
        EFINIXPLL.__init__(self, platform, n, version="V3")

# Efinix / TRION ----------------------------------------------------------------------------------

class TRIONPLL(EFINIXPLL):
    nclkouts_max = 3
    def __init__(self, platform, n=0):
        EFINIXPLL.__init__(self, platform, n, version="V1_V2")
