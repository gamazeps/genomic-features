import pandas as pd
import pytest

import genomic_features as gf
from genomic_features import filters


@pytest.fixture(scope="module")
def hsapiens108():
    return gf.ensembl.annotation("Hsapiens", 108)


# TODO: "exons" is very slow for large results, should figure out how to handle that
@pytest.fixture(
    params=["genes", "transcripts", pytest.param("exons", marks=pytest.mark.slow)]
)
def table_method(request):
    def getter(db):
        return getattr(db, request.param)

    return getter


def _filter_id_func(filt) -> str:
    """Generate test id for filter."""
    return f"{filt.__class__.__name__}_{filt.value}"


@pytest.mark.parametrize(
    "filt",
    [
        filters.GeneIDFilter("ENSG00000000003"),
        filters.GeneIDFilter("ENSG00000000460"),
        filters.GeneIDFilter("LRG_997"),
        filters.GeneBioTypeFilter("transcribed_processed_pseudogene"),
        filters.GeneBioTypeFilter("TR_C_gene"),
        filters.GeneNameFilter("TSPAN6"),
        filters.TxIDFilter("ENST00000513666"),
        filters.TxBioTypeFilter("transcribed_processed_pseudogene"),
        filters.SeqNameFilter("1"),
        filters.SeqNameFilter("MT"),
        filters.UniProtIDFilter("F5H4R2.65"),
        filters.UniProtDBFilter("Uniprot_isoform"),
        filters.UniProtMappingTypeFilter("SEQUENCE_MATCH"),
        filters.ExonIDFilter("ENSE00001639513"),
    ],
    ids=_filter_id_func,
)
def test_equality_filter_single(hsapiens108, filt, table_method):
    func = table_method(hsapiens108)
    result = func(filter=filt)[list(filt.columns())[0]]
    assert set(result) == {filt.value}


@pytest.mark.parametrize(
    "filt",
    [
        filters.GeneIDFilter(["ENSG00000000003", "ENSG00000093183"]),
        filters.GeneBioTypeFilter(["TR_J_gene", "TR_V_gene"]),
        filters.GeneNameFilter(["TSPAN6", "TNMD"]),
        filters.SeqNameFilter(["1", "2"]),
        filters.TxIDFilter(["ENST00000537657", "ENST00000341376"]),
        filters.TxBioTypeFilter(["processed_pseudogene", "unprocessed_pseudogene"]),
        filters.UniProtIDFilter(["A0A804HIK9.2", "G5E9P6.85"]),
        filters.UniProtDBFilter(["SWISSPROT", "Uniprot_isoform"]),
        filters.UniProtMappingTypeFilter(["DIRECT"]),  # Only two kinds in this DB
        filters.ExonIDFilter(["ENSE00001639513", "ENSE00001923809"]),
    ],
    ids=_filter_id_func,
)
def test_equality_filter_list(hsapiens108, filt, table_method):
    func = table_method(hsapiens108)
    result = func(filter=filt)[list(filt.columns())[0]]
    assert set(result) == set(filt.value)


def test_canonical(hsapiens108, table_method):
    func = table_method(hsapiens108)
    result = func(
        cols=["tx_id", "canonical_transcript"], filter=filters.CanonicalTxFilter()
    )

    assert result["tx_is_canonical"].sum() == result.shape[0]
    pd.testing.assert_series_equal(
        result["tx_id"].rename("canonical_transcript"), result["canonical_transcript"]
    )

    result_non_canonical = func(
        cols=["tx_id", "canonical_transcript"], filter=~filters.CanonicalTxFilter()
    )

    assert result_non_canonical["tx_is_canonical"].sum() == 0
    assert (
        result_non_canonical["canonical_transcript"] == result_non_canonical["tx_id"]
    ).sum() == 0


# These are not working quite as expected:
# https://github.com/ibis-project/ibis/issues/6096
def test_and_filter(hsapiens108):
    assert (
        hsapiens108.genes(
            filter=(
                filters.GeneBioTypeFilter("protein_coding")
                & filters.GeneBioTypeFilter("TR_C_gene")
            )
        ).shape[0]
        == 0
    )
    assert (
        hsapiens108.genes(
            filter=(
                filters.GeneBioTypeFilter("protein_coding")
                & filters.GeneIDFilter(
                    ["LRG_997", "ENSG00000000460", "ENSG00000000003"]
                )
            )
        ).shape[0]
        == 2
    )


def test_or_filter(hsapiens108):
    assert (
        hsapiens108.genes(
            filter=(
                filters.GeneBioTypeFilter("protein_coding")
                | filters.GeneBioTypeFilter("TR_C_gene")
            )
        ).shape[0]
        == hsapiens108.genes()["gene_biotype"]
        .isin(["protein_coding", "TR_C_gene"])
        .sum()
    )
    assert (
        hsapiens108.genes(
            filter=(
                filters.GeneIDFilter("LRG_997")
                | filters.GeneIDFilter(
                    ["LRG_997", "ENSG00000000460", "ENSG00000000003"]
                )
            )
        ).shape[0]
        == 3
    )


def test_range_filter(hsapiens108):
    any_overlap_filter = hsapiens108.genes(
        filter=filters.GeneRangesFilter("1:77000000-78000000")
    )
    within_overlap_filter = hsapiens108.genes(
        filter=filters.GeneRangesFilter("1:77000000-78000000", type="within")
    )
    assert all(within_overlap_filter.seq_name == "1") & all(
        any_overlap_filter.seq_name == "1"
    )
    assert any_overlap_filter.shape[0] > within_overlap_filter.shape[0]
    assert (all(within_overlap_filter.gene_seq_start >= 77000000)) & (
        all(within_overlap_filter.gene_seq_end <= 78000000)
    )
    assert (all(any_overlap_filter.gene_seq_end >= 77000000)) & (
        all(any_overlap_filter.gene_seq_start <= 78000000)
    )
    # Test input
    with pytest.raises(ValueError):
        hsapiens108.genes(filter=filters.GeneRangesFilter("1_77000000_78000000"))

    with pytest.raises(ValueError):
        hsapiens108.genes(filter=filters.GeneRangesFilter("1-77000000-78000000"))

    with pytest.raises(ValueError):
        hsapiens108.genes(
            filter=filters.GeneRangesFilter("1:77000000-78000000", type="start")
        )


def test_negation(hsapiens108):
    result = hsapiens108.genes(filter=~filters.GeneBioTypeFilter("protein_coding"))
    assert "protein_coding" not in result["gene_biotype"]

    result = hsapiens108.genes(
        filter=filters.GeneIDFilter("ENSG00000000003")
        & ~filters.GeneBioTypeFilter("protein_coding")
    )
    assert result.shape[0] == 0

    result = hsapiens108.genes(
        filter=~filters.GeneIDFilter("ENSG00000000003")
        & filters.GeneBioTypeFilter("protein_coding")
    )
    assert {"protein_coding"} == set(result["gene_biotype"])
    assert "ENSG00000000003" not in result["gene_id"]
    assert result.shape[0] == 22894


@pytest.mark.parametrize("backend", ["sqlite", "duckdb"])
def test_seqs_as_int(backend):
    hsapiens108 = gf.ensembl.annotation("Hsapiens", 108, backend=backend)

    result_w_int = hsapiens108.genes(filter=filters.SeqNameFilter(1))
    result_w_str = hsapiens108.genes(filter=filters.SeqNameFilter("1"))
    pd.testing.assert_frame_equal(
        result_w_int,
        result_w_str,
    )

    result_w_ints = hsapiens108.genes(filter=filters.SeqNameFilter([1, 2]))
    result_w_strs = hsapiens108.genes(filter=filters.SeqNameFilter(["1", "2"]))
    result_w_mixed = hsapiens108.genes(filter=filters.SeqNameFilter([1, "2"]))

    pd.testing.assert_frame_equal(
        result_w_ints,
        result_w_strs,
    )
    pd.testing.assert_frame_equal(
        result_w_ints,
        result_w_mixed,
    )
