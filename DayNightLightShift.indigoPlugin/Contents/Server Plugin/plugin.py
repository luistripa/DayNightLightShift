import dataclasses
from enum import Enum

import indigo


class Mode(Enum):
    DAY = 'day'
    NIGHT = 'night'


@dataclasses.dataclass
class Shift:
    device_id: int
    onOffState: bool
    mode: Mode
    day_device_id: int
    night_device_id: int

    @property
    def current_shift_device_id(self) -> int:
        if self.mode == 'day':
            return self.day_device_id
        else:
            return self.night_device_id

    def turn_on(self):
        shift_device = indigo.devices[self.device_id]
        device = indigo.devices[self.current_shift_device_id]
        indigo.device.turnOn(device.id)

        # Update states
        self.onOffState = True
        shift_device.updateStateOnServer('onOffState', True)

    def turn_off(self):
        shift_device = indigo.devices[self.device_id]
        device = indigo.devices[self.current_shift_device_id]
        indigo.device.turnOff(device.id)

        # Update states
        self.onOffState = False
        shift_device.updateStateOnServer('onOffState', False)

    def __hash__(self):
        return self.device_id


STATES = ['day', 'night']


class Plugin(indigo.PluginBase):

    def startup(self) -> None:
        self.shifts: dict[int, Shift] = dict()
        """
        A dictionary that stores the shifts that are being processed by the plugin.
        The key is the shift's indigo device id and the value is the shift object.
        """

        self.device_to_shifts: dict[int, set[Shift]] = dict()
        """
        A dictionary which shifts are monitoring a specific device.
        The key is the indigo device id and the value is a set of shifts.
        """
        indigo.devices.subscribeToChanges()

    def deviceStartComm(self, dev: indigo.Device) -> None:
        if dev.states.get('mode') is None or dev.states.get('mode') not in STATES:
            dev.updateStateOnServer('mode', dev.pluginProps['default_mode'])

        shift = Shift(
            device_id=dev.id,
            onOffState=False,
            mode=dev.states.get('mode'),
            day_device_id=int(dev.pluginProps['day_device_id']),
            night_device_id=int(dev.pluginProps['night_device_id'])
        )

        # Add the shift to the day and night devices
        self.device_to_shifts.setdefault(int(dev.pluginProps['day_device_id']), set()).add(shift)
        self.device_to_shifts.setdefault(int(dev.pluginProps['night_device_id']), set()).add(shift)

        # Add the shift to the shifts dictionary
        self.shifts[dev.id] = shift

        self.logger.info(f'Shift "{dev.name}" started successfully')

    def deviceStopComm(self, dev: indigo.Device) -> None:
        device_id = int(dev.id)
        shift = self.shifts.pop(device_id)

        # Remove the shift from the day device and remove the device from the dictionary if it has no shifts
        self.device_to_shifts[shift.day_device_id].remove(shift)
        if len(self.device_to_shifts[shift.day_device_id]) == 0:
            self.device_to_shifts.pop(shift.day_device_id)

        # Remove the shift from the night device and remove the device from the dictionary if it has no shifts
        self.device_to_shifts[shift.night_device_id].remove(shift)
        if len(self.device_to_shifts[shift.night_device_id]) == 0:
            self.device_to_shifts.pop(shift.night_device_id)

        self.logger.info(f'Shift "{dev.name}" stopped successfully')

    def runConcurrentThread(self):
        try:
            while True:
                self.sleep(1)
        except self.StopThread:
            pass

    def deviceUpdated(self, orig_dev: indigo.Device, new_dev: indigo.Device) -> None:
        new_device_id = int(new_dev.id)
        shifts = self.device_to_shifts.get(new_device_id)
        if shifts is None:
            return

        for shift in shifts:
            if shift.mode == 'day' and shift.day_device_id == new_device_id:
                shift.onOffState = new_dev.states.get('onOffState')
                shift_device = indigo.devices[shift.device_id]
                shift_device.updateStateOnServer('onOffState', new_dev.states.get('onOffState'))

            elif shift.mode == 'night' and shift.night_device_id == new_device_id:
                shift.onOffState = new_dev.states.get('onOffState')
                shift_device = indigo.devices[shift.device_id]
                shift_device.updateStateOnServer('onOffState', new_dev.states.get('onOffState'))


    def _get_shifts_for_device_id(self, device_id: int) -> list[Shift]:
        shifts = []
        for shift in self.shifts.values():
            if shift.day_device_id == device_id or shift.night_device_id == device_id:
                shifts.append(shift)
        return shifts

    def actionControlDevice(self, action):
        shift_device: indigo.Device = indigo.devices[action.deviceId]
        if action.deviceAction == indigo.kDeviceAction.TurnOn:
            self.logger.info(f'sent "{shift_device.name}" on')
            self.turn_on_shift(action)

        elif action.deviceAction == indigo.kDeviceAction.TurnOff:
            self.logger.info(f'sent {shift_device.name} off')
            self.turn_off_shift(action)

        elif action.deviceAction == indigo.kDeviceAction.RequestStatus:
            self.logger.info(f'sent "{shift_device.name}" status request')
            shift = self.shifts.get(action.deviceId)
            monitored_device = indigo.devices[shift.current_shift_device_id]
            monitored_device.refreshFromServer()

            shift_device.updateStateOnServer('onOffState', shift.onOffState)
            shift_device.updateStateOnServer('mode', shift.mode)
            shift_device.updateStateOnServer('onOffState', monitored_device.states.get('onOffState'))

    def turn_on_shift(self, action):
        shift = self.shifts.get(action.deviceId)

        device = indigo.devices[shift.current_shift_device_id]

        shift_device = indigo.devices[shift.device_id]
        shift_device.updateStateOnServer('onOffState', True)

        indigo.device.turnOn(device.id)

    def turn_off_shift(self, action):
        shift = self.shifts.get(action.deviceId)

        device = indigo.devices[shift.current_shift_device_id]

        shift_device = indigo.devices[shift.device_id]
        shift_device.updateStateOnServer('onOffState', False)

        indigo.device.turnOff(device.id)

    # Actions
    def set_shift(self, action):
        shift_id = action.deviceId
        mode = action.props['mode']

        shift = self.shifts.get(shift_id)
        shift.mode = mode

        device = indigo.devices[shift_id]
        device.updateStateOnServer('mode', mode)

        if shift.onOffState:
            if mode == 'day':
                indigo.device.turnOn(shift.day_device_id)
                indigo.device.turnOff(shift.night_device_id)
            else:
                indigo.device.turnOn(shift.night_device_id)
                indigo.device.turnOff(shift.day_device_id)

        self.logger.info(f'Shift {shift_id} ({device.name}) set to {mode}')
