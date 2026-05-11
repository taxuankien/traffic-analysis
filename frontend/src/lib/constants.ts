export const API_BASE = '/api';

export const WS_BASE = (() => {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${proto}//${window.location.host}`;
})();

export const VEHICLE_CLASS_MAP: Record<number, string> = {
  2: 'car',
  3: 'motorcycle',
  5: 'bus',
  7: 'truck',
};

export const VEHICLE_CLASSES = [
  { id: 2, name: 'Car' },
  { id: 3, name: 'Motorcycle' },
  { id: 5, name: 'Bus' },
  { id: 7, name: 'Truck' },
];
