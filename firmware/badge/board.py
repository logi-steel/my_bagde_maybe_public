"""Create the display driver from the hardware section of the config."""
from machine import Pin, SPI
from .epd import EPD


def make_epd(hw):
    spi = SPI(hw.get("spi_id", 1), baudrate=4000000, polarity=0, phase=0,
              sck=Pin(hw["sck"]), mosi=Pin(hw["mosi"]), miso=Pin(hw["miso"]))
    return EPD(spi, cs=hw["cs"], dc=hw["dc"], rst=hw["rst"], busy=hw["busy"])
