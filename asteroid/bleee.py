
import xml
import pydbus as dbus

# Hacky Bluez dbus interface wrapper: TODO: Improve

BLUEZ_BUS = "org.bluez"

class DbusWrapper:

    _dbus_extra_names = {}

    def __init__(self, bus_name, object_path=None, bus=None):
        if not bus:
            bus = dbus.SystemBus()
        if len(object_path) > 1:
            object_path = object_path.rstrip("/")
        self.bus = bus
        self.bus_name = bus_name
        self.object_path = object_path
        self.dbus_obj = bus.get(bus_name, object_path)

    def __getattr__(self, name):
        if name in self._dbus_extra_names:
            name = self._dbus_extra_names[name]
        else:
            name = "".join(map(lambda s: s.capitalize(), name.split("_")))
        return getattr(self.dbus_obj, name)

    def introspect(self):
        return xml.etree.ElementTree.fromstring(self.dbus_obj.Introspect())

    def create_child(self, postfix):
        postfix = postfix.strip("/")
        return DbusWrapper(self.bus_name, self.object_path + "/" + postfix, bus=self.bus)

    def list_children_info(self, depth=1):
        prefix = self.object_path
        objman = DbusWrapper(self.bus_name, "/", bus=self.bus)
        for k, v in objman.get_managed_objects().items():
            if k.startswith(prefix) and (depth is None or len(k[len(prefix):].split("/")) == (depth + 1)):
                yield k, v


class BLECharacteristic(DbusWrapper):

    _dbus_extra_names = {"uuid": "UUID"}

    def write(self, data):
        self.write_value(bytes(data), {})

    def read(self):
        return bytes(self.read_value({}))

class BLEService(DbusWrapper):

    @property
    def characteristics(self):
        for k, v in self.list_children_info():
            yield BLECharacteristic(BLUEZ_BUS, k, bus=self.bus)


class BLEDevice(DbusWrapper):

    @property
    def services(self):
        for k, v in self.list_children_info():
            yield BLEService(BLUEZ_BUS, k, bus=self.bus)

    @property
    def characteristics(self):
        for serv in self.services:
            for char in serv.characteristics:
                yield char

    def char_by_uuid(self, uuid):
        for c in self.characteristics:
            if c.uuid == uuid:
                return c
        raise IOError("UUID '%s' not present on the device" % uuid)


class BLE(DbusWrapper):

    def __init__(self, controller=None):
        if controller is None:
            # TODO: Add actual auto controller selection
            controller = "hci0"
        super(BLE, self).__init__(BLUEZ_BUS, "/org/bluez/" + controller)

    def device_by_address(self, address):
        for dev in self.devices:
            if dev.address == address:
                return dev
        raise IOError("Device with address %s not found" % address)

    @property
    def devices(self):
        for k, v in self.list_children_info():
            yield BLEDevice(BLUEZ_BUS, k, bus=self.bus)
