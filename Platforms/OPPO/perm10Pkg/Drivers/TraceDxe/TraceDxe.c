/** @file
  PERM10 bring-up beacon: paint the splash framebuffer as soon as DXE starts
  dispatching, so DXE progress is visible without a serial port.
**/

#include <Uefi.h>
#include <Library/BaseMemoryLib.h>
#include <Library/UefiDriverEntryPoint.h>
#include <Library/MemoryMapHelperLib.h>
#include <Library/ArmSmcLib.h>

STATIC
VOID
Perm10Paint (
  IN UINT32  Colour
  )
{
  EFI_MEMORY_REGION_DESCRIPTOR  Region;
  UINT32                       *Pixels;
  UINTN                         Count;
  UINTN                         Index;

  Region.Address = 0;
  Region.Length  = 0;
  LocateMemoryRegionByName ("Display Reserved", &Region);
  LocateMemoryRegionByName ("Display_Reserved", &Region);
  if ((Region.Address == 0) || (Region.Length == 0)) {
    return;
  }

  Pixels = (UINT32 *)(UINTN)Region.Address;
  Count  = Region.Length / sizeof (UINT32);
  for (Index = 0; Index < Count; Index++) {
    Pixels[Index] = Colour;
  }
}

EFI_STATUS
EFIAPI
TraceDxeEntryPoint (
  IN EFI_HANDLE        ImageHandle,
  IN EFI_SYSTEM_TABLE  *SystemTable
  )
{
  Perm10Paint (0x00FF8000); // orange: DXE is dispatching
  return EFI_SUCCESS;
}
