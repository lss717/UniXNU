/** @file
  FdtLib compatibility shim for the older edk2 used by edk2-msm8998.

  UniXNU is written against the newer MdePkg BaseFdtLib API
  (<Library/FdtLib.h>).  The msm8998 tree still carries the older
  EmbeddedPkg FdtLib, which exposes the raw libfdt names.  These
  wrappers map the new names onto the old library so the same UniXNU
  sources build without a second edk2 checkout.

  SPDX-License-Identifier: BSD-2-Clause-Patent
**/

#pragma once

#include <libfdt.h>

typedef struct {
  UINT32    Magic;
  UINT32    TotalSize;
  UINT32    OffsetDtStruct;
  UINT32    OffsetDtStrings;
  UINT32    OffsetMemRsvmap;
  UINT32    Version;
  UINT32    LastCompVersion;
  UINT32    BootCpuidPhys;
  UINT32    SizeDtStrings;
  UINT32    SizeDtStruct;
} FDT_HEADER;

#define Fdt32ToCpu                  fdt32_to_cpu
#define Fdt64ToCpu                  fdt64_to_cpu
#define FdtCheckHeader              fdt_check_header
#define FdtTotalSize(Fdt)           fdt_totalsize ((Fdt))
#define FdtPathOffset               fdt_path_offset
#define FdtGetProp                  fdt_getprop
#define FdtSetProp                  fdt_setprop
#define FdtDelProp                  fdt_delprop
#define FdtAddSubnode               fdt_add_subnode
#define FdtDelNode                  fdt_del_node
#define FdtOpenInto                 fdt_open_into
#define FdtPack                     fdt_pack
#define FdtOverlayApply             fdt_overlay_apply
#define FdtStrerror                 fdt_strerror
#define FdtSubnodeOffsetNameLen     fdt_subnode_offset_namelen

STATIC
inline
CONST CHAR8 *
FdtString (
  IN CONST VOID   *Fdt,
  IN CONST CHAR8  *NodePath,
  IN CONST CHAR8  *Name
  )
{
  INT32  Node;

  Node = fdt_path_offset (Fdt, NodePath);
  if (Node < 0) {
    return NULL;
  }

  return fdt_getprop (Fdt, Node, Name, NULL);
}
