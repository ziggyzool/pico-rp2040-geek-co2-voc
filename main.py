# sgp30_lcd_adafruit.py
from machine import Pin, SPI, I2C, PWM
import time
import adafruit_sgp30
import framebuf, micropython

# --- LCD pins ---
BL = 25
DC = 8
CS = 9
SCK = 10
MOSI = 11
RST = 12

# --- Full LCD_1inch14 class ---
class LCD_1inch14(framebuf.FrameBuffer):
    def __init__(self):
        self.width = 240
        self.height = 135
        self.cs = Pin(CS,Pin.OUT)
        self.rst = Pin(RST,Pin.OUT)
        self.cs(1)
        self.spi = SPI(1,50_000_000,polarity=0, phase=0,sck=Pin(SCK),mosi=Pin(MOSI),miso=None)
        self.dc = Pin(DC,Pin.OUT)
        self.dc(1)
        self.buffer = bytearray(self.height * self.width * 2)
        super().__init__(self.buffer, self.width, self.height, framebuf.RGB565)
        self.init_display()
        self.red   =   0x07E0
        self.green =   0x001f
        self.blue  =   0xf800
        self.white =   0xffff

    def write_cmd(self, cmd):
        self.cs(1); self.dc(0); self.cs(0)
        self.spi.write(bytearray([cmd])); self.cs(1)

    def write_data(self, buf):
        self.cs(1); self.dc(1); self.cs(0)
        if isinstance(buf, int):
            self.spi.write(bytearray([buf]))
        else:
            self.spi.write(buf)
        self.cs(1)

    def init_display(self):
        self.rst(1); self.rst(0); self.rst(1)
        self.write_cmd(0x36); self.write_data(0x70)
        self.write_cmd(0x3A); self.write_data(0x05)
        self.write_cmd(0xB2); self.write_data(bytes([0x0C,0x0C,0x00,0x33,0x33]))
        self.write_cmd(0xB7); self.write_data(0x35)
        self.write_cmd(0xBB); self.write_data(0x19)
        self.write_cmd(0xC0); self.write_data(0x2C)
        self.write_cmd(0xC2); self.write_data(0x01)
        self.write_cmd(0xC3); self.write_data(0x12)
        self.write_cmd(0xC4); self.write_data(0x20)
        self.write_cmd(0xC6); self.write_data(0x0F)
        self.write_cmd(0xD0); self.write_data(bytes([0xA4,0xA1]))
        self.write_cmd(0xE0); self.write_data(bytes([0xD0,0x04,0x0D,0x11,0x13,0x2B,0x3F,0x54,0x4C,0x18,0x0D,0x0B,0x1F,0x23]))
        self.write_cmd(0xE1); self.write_data(bytes([0xD0,0x04,0x0C,0x11,0x13,0x2C,0x3F,0x44,0x51,0x2F,0x1F,0x1F,0x20,0x23]))
        self.write_cmd(0x21)
        self.write_cmd(0x11)
        self.write_cmd(0x29)

    @micropython.viper
    def swap(self):
        buf = ptr8(self.buffer)
        for x in range(0,240*135*2,2):
            tt = buf[x]; buf[x] = buf[x+1]; buf[x+1] = tt

    @micropython.viper
    def ins(self, ins_data, ins_len:int, start:int):
        ins_buf = ptr8(ins_data); buf = ptr8(self.buffer)
        for x in range(ins_len):
            buf[start + x] = ins_buf[x]

    @micropython.viper
    def mirror(self):
        buf = ptr8(self.buffer)
        for y in range(0,135):
            for x in range(0,120):
                temp_x = (240 - x) * 2
                temp_y = y * 480
                t1 = buf[x*2 + temp_y]
                t2 = buf[x*2 + temp_y + 1]
                buf[x*2 + temp_y] = buf[temp_x + temp_y]
                buf[x*2 + temp_y + 1] = buf[temp_x + temp_y + 1]
                buf[temp_x + temp_y] = t1
                buf[temp_x + temp_y + 1] = t2

    def show(self):
        self.write_cmd(0x2A)
        self.write_data(bytes([0x00,0x28,0x01,0x17]))
        self.write_cmd(0x2B)
        self.write_data(bytes([0x00,0x35,0x00,0xBB]))
        self.write_cmd(0x2C)
        self.cs(1); self.dc(1); self.cs(0)
        self.swap()
        self.spi.write(self.buffer)
        self.swap()
        self.cs(1)

# --- I2C setup & safe SGP30 init ---
# Change these pins if your wiring uses different GP pins
sdaPIN = Pin(28)
sclPIN = Pin(29)
i2c_1 = I2C(0, sda=sdaPIN, scl=sclPIN, freq=100000)
time.sleep(0.05)

# Initialize LCD and backlight first so we can show messages
pwm = PWM(Pin(BL))
pwm.freq(90000)
pwm.duty_u16(04500)
lcd = LCD_1inch14()
lcd.fill(0xffff)
lcd.show()

def lcd_print(line1, line2="", line3=""):
    lcd.fill(0xffff)
    lcd.text(line1, 20, 10, 0x001F)
    lcd.text(line2, 20, 40, 0x001F)
    if line3:
        lcd.text(line3, 20, 70, 0x001F)
    lcd.show()

lcd_print("I2C scanning...", "")
time.sleep(0.1)
try:
    devices = i2c_1.scan()
except Exception as e:
    lcd_print("I2C scan failed", str(e))
    raise

lcd_print("I2C scan:", str(devices))
time.sleep(1)

if 0x58 not in devices:
    lcd_print("SGP30 not found", "Check wiring/VCC")
    # also print to REPL for debugging
    print("I2C devices:", devices)
    raise OSError("SGP30 (0x58) not found on I2C bus")

# Safe creation of SGP30
try:
    sgp = adafruit_sgp30.Adafruit_SGP30(i2c_1, address=0x58)
except Exception as e:
    lcd_print("SGP30 init fail", str(e))
    raise

lcd_print("SGP30 init OK", "warming..."); time.sleep(1)

# Main loop: read, display, log
while True:
    try:
        co2eq, tvoc = sgp.iaq_measure()
    except OSError:
        lcd_print("I2C read error", "Check wiring")
        time.sleep(1)
        continue
    except Exception as e:
        lcd_print("SGP30 error", str(e))
        time.sleep(1)
        continue

    if co2eq == 400 and tvoc == 0:
        lcd_print("SGP30 warming", "stabilizing...")
    else:
        lcd_print("CO2: {} ppm".format(co2eq),
                  "TVOC: {} ppb".format(tvoc),
                  "Logging to data.csv")
        try:
            with open("data.csv", "a") as f:
                f.write("{},{}\n".format(co2eq, tvoc))
        except OSError:
            pass

    time.sleep(0.5)
