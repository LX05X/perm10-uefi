#include <Library/ConfigurationMapLib.h>

// Generated from the PERM10 605 XBL uefiplatLA.cfg by generate_configuration_map.py.
// Only keys already mapped by the Kodiak package are emitted; values are PERM10's.
STATIC EFI_CONFIGURATION_ENTRY_DESCRIPTOR gConfigurationDescriptor[] = {
  { "NumCpusFuseAddr", 0x5c04c },
  { "EnableShell", 0x1 },
  { "InitialPagePoolCount", 0x1000 },
  { "SharedIMEMBaseAddr", 0x146aa000 },
  { "DloadCookieAddr", 0x1fd3000 },
  { "DloadCookieValue", 0x10 },
  { "NumCpus", 0x8 },
  { "NumActiveCores", 0x8 },
  { "MaxLogFileSize", 0x400000 },
  { "UefiMemUseThreshold", 0xe1 },
  { "USBHS1_Config", 0x0 },
  { "UsbFnIoRevNum", 0x10001 },
  { "PwrBtnShutdownFlag", 0x0 },
  { "Sdc1GpioConfigOn", 0x1e92 },
  { "Sdc2GpioConfigOn", 0x1e92 },
  { "Sdc1GpioConfigOff", 0xa00 },
  { "Sdc2GpioConfigOff", 0xa00 },
  { "EnableSDHCSwitch", 0x1 },
  { "EnableUfsIOC", 0x1 },
  { "UfsSmmuConfigForOtherBootDev", 0x1 },
  { "UEFIExitUfsSSURequired", 0x1 },
  { "SecurityFlag", 0xc4 },
  { "DetectRetailUserAttentionHotkey", 0x0 },
  { "DetectRetailUserAttentionHotkeyCode", 0x17 },
  { "EnableOEMSetupAppInRetail", 0x0 },
  { "EnableLogFsSyncInRetail", 0x0 },
  { "ShmBridgememSize", 0xa00000 },
  { "EnableMultiThreading", 0x1 },
  { "MaxCoreCnt", 0x8 },
  { "EarlyInitCoreCnt", 0x2 },
  { "EnableUefiSecAppDebugLogDump", 0x0 },
  { "AllowNonPersistentVarsInRetail", 0x1 },
  { "EnableDisplayThread", 0x0 },
  { "EnableDisplayImageFv", 0x0 },
  { "DDRInfoNotifyFlag", 0x0 },
  { "EnableVariablePolicyEngine", 0x0 },
  { "EnableACPIFallback", 0x0 },
};

VOID GetConfigurationMap (OUT EFI_CONFIGURATION_ENTRY_DESCRIPTOR **ConfigurationDescriptor, OUT UINT8 *ConfigurationDescriptorCount) {
  *ConfigurationDescriptor = gConfigurationDescriptor;
  *ConfigurationDescriptorCount = ARRAY_SIZE (gConfigurationDescriptor);
}
