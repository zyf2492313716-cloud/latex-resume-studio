import { Capacitor, registerPlugin } from '@capacitor/core';

const Tectonic = registerPlugin('Tectonic');

export function canUseNativeTectonic() {
  return Capacitor.isNativePlatform();
}

export async function getNativeTectonicStatus() {
  if (!canUseNativeTectonic()) {
    return {
      available: false,
      error: '当前不是 Android/iOS 原生运行环境。'
    };
  }

  if (!Tectonic?.status) {
    return {
      available: false,
      error: '当前 APK 未注册 Tectonic 原生插件。'
    };
  }

  return Tectonic.status();
}
