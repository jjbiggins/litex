import sys

from litex.tools.litex_client import RemoteClient

def get_data_mod(data_type, data_name):
    """Get the pythondata-{}-{} module or raise a useful error message."""
    imp = f"import pythondata_{data_type}_{data_name} as dm"
    try:
        l = {}
        exec(imp, {}, l)
        return l['dm']
    except ImportError as e:
        raise ImportError("""\
pythondata-{dt}-{dn} module not installed! Unable to use {dn} {dt}.
{e}

You can install this by running;
 pip3 install git+https://github.com/litex-hub/pythondata-{dt}-{dn}.git
""".format(dt=data_type, dn=data_name, e=e))
