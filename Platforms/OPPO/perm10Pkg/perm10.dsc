[Defines]
  PLATFORM_NAME                  = perm10
  PLATFORM_GUID                  = 4E5D6B70-3F6B-4A9B-9C10-22831A210750
  PLATFORM_VERSION               = 0.1
  DSC_SPECIFICATION              = 0x00010005
  OUTPUT_DIRECTORY               = Build/perm10Pkg
  SUPPORTED_ARCHITECTURES        = AARCH64
  BUILD_TARGETS                  = RELEASE|DEBUG
  SKUID_IDENTIFIER               = DEFAULT
  FLASH_DEFINITION               = perm10Pkg/perm10.fdf
  USE_CUSTOM_DISPLAY_DRIVER      = 1
  SOC_TYPE                       = 0

!include KodiakPkg/KodiakPkg.dsc.inc

[PcdsFixedAtBuild]
  gArmTokenSpaceGuid.PcdSystemMemoryBase|0x80000000
  gArmPlatformTokenSpaceGuid.PcdCPUCoresStackBase|0x9FF90000
  gArmPlatformTokenSpaceGuid.PcdCPUCorePrimaryStackSize|0x40000

  gSiliciumPkgTokenSpaceGuid.PcdSmbiosSystemManufacturer|"OPPO"
  gSiliciumPkgTokenSpaceGuid.PcdSmbiosSystemModel|"K10 Vitality"
  gSiliciumPkgTokenSpaceGuid.PcdSmbiosSystemRetailModel|"PERM10"
  gSiliciumPkgTokenSpaceGuid.PcdSmbiosSystemRetailSku|"PERM10-22831-12GB"
  gSiliciumPkgTokenSpaceGuid.PcdSmbiosSystemBoardModel|"Walle 21075/22831"
  gSiliciumPkgTokenSpaceGuid.PcdFrameBufferWidth|1080
  gSiliciumPkgTokenSpaceGuid.PcdFrameBufferHeight|2412
  gSiliciumPkgTokenSpaceGuid.PcdFrameBufferColorDepth|32
  gQcomPkgTokenSpaceGuid.PcdPlatformType|"LA"
  gQcomPkgTokenSpaceGuid.PcdStorageIsUfs3|FALSE

[BuildOptions]
  # Enables the Perm10Trace framebuffer beacons in SiliciumPkg/Sec.
  *_*_AARCH64_CC_FLAGS = -DPERM10_SEC_TRACE=1 -DPERM10_HALT_LEVEL=0

[LibraryClasses]
  MemoryMapLib|perm10Pkg/Library/MemoryMapLib/MemoryMapLib.inf
  ConfigurationMapLib|perm10Pkg/Library/ConfigurationMapLib/ConfigurationMapLib.inf

[Components]
  # ACPI disabled until a PERM10 DSDT/SSDT is generated and validated.

  # Bring-up beacon, paints the framebuffer when DXE starts dispatching.
  perm10Pkg/Drivers/TraceDxe/TraceDxe.inf
