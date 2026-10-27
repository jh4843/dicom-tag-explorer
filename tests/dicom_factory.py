# 테스트용 DICOM 파일을 pydicom으로 생성한다 (식별 정보 없는 가짜 값만 사용).
from __future__ import annotations

from pathlib import Path

from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.encaps import encapsulate
from pydicom.sequence import Sequence
from pydicom.uid import (
    ExplicitVRLittleEndian, ImplicitVRLittleEndian, JPEGBaseline8Bit, generate_uid,
)

WSI_SOP = "1.2.840.10008.5.1.4.1.1.77.1.6"
SC_SOP = "1.2.840.10008.5.1.4.1.1.7"


def _meta(sop_class: str, sop_inst: str, ts: str) -> FileMetaDataset:
    m = FileMetaDataset()
    m.MediaStorageSOPClassUID = sop_class
    m.MediaStorageSOPInstanceUID = sop_inst
    m.TransferSyntaxUID = ts
    m.ImplementationClassUID = "1.2.3.4"
    return m


def make_dataset(sop_class: str = SC_SOP, ts: str = ExplicitVRLittleEndian) -> Dataset:
    ds = Dataset()
    ds.SOPClassUID = sop_class
    ds.SOPInstanceUID = generate_uid()
    ds.file_meta = _meta(sop_class, ds.SOPInstanceUID, ts)
    return ds


def write(ds: Dataset, path: Path, implicit: bool = False) -> Path:
    ds.save_as(path, enforce_file_format=True, implicit_vr=implicit if implicit else None)
    return path


def nested_file(path: Path, undefined: bool = True, implicit: bool = False) -> Path:
    """Undefined Length SQ/Item + 사설 태그 + 문자셋이 있는 파일."""
    ts = ImplicitVRLittleEndian if implicit else ExplicitVRLittleEndian
    ds = make_dataset(ts=ts)
    ds.SpecificCharacterSet = "ISO_IR 192"
    ds.PatientName = "테스트^환자"
    ds.Modality = "OT"
    inner = Dataset()
    inner.CodeValue = "A1"
    inner.CodeMeaning = "첫째"
    inner2 = Dataset()
    inner2.CodeValue = "B2"
    seq = Sequence([inner, inner2])
    ds.ConceptNameCodeSequence = seq
    if undefined:
        ds["ConceptNameCodeSequence"].is_undefined_length = True
        for it in seq:
            it.is_undefined_length_sequence_item = True
    ds.add_new(0x00090010, "LO", "TEST CREATOR")
    ds.add_new(0x00091001, "LO", "private value")
    ds.add_new(0x00091002, "OB", b"\x01\x02\x03")
    ds.Rows = 2
    ds.Columns = 2
    return write(ds, path, implicit=implicit)


def encapsulated_file(path: Path, frames: int = 3, sop_class: str = SC_SOP, has_bot: bool = True) -> Path:
    ds = make_dataset(sop_class=sop_class, ts=JPEGBaseline8Bit)
    ds.Rows = 8
    ds.Columns = 8
    ds.SamplesPerPixel = 1
    ds.BitsAllocated = 8
    ds.BitsStored = 8
    ds.HighBit = 7
    ds.PixelRepresentation = 0
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.NumberOfFrames = frames
    ds.PixelData = encapsulate([bytes([i]) * 10 for i in range(frames)], has_bot=has_bot)
    ds["PixelData"].is_undefined_length = True
    ds["PixelData"].VR = "OB"
    return write(ds, path)


def mono_file(path: Path, photometric: str = "MONOCHROME1") -> Path:
    """VOI 없는 8bit 흑백 2x2 (값 10, 20, 30, 40)."""
    ds = make_dataset()
    ds.Rows = 2
    ds.Columns = 2
    ds.SamplesPerPixel = 1
    ds.BitsAllocated = 8
    ds.BitsStored = 8
    ds.HighBit = 7
    ds.PixelRepresentation = 0
    ds.PhotometricInterpretation = photometric
    ds.PixelData = bytes([10, 20, 30, 40])
    return write(ds, path)


def long_text_file(path: Path, value: str) -> Path:
    ds = make_dataset()
    ds.add_new(0x00204000, "LT", value)  # ImageComments
    ds.PatientName = "Test^Dummy"
    return write(ds, path)
