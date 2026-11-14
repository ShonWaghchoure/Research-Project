"""The Python shortfall leaf must equal Settlement's keccak256(abi.encode(id, seller, buyer, wh))
or every shortfall proof fails on chain. Vector computed independently with ethers.js."""

from app.chain.merkle import shortfall_leaf


def test_shortfall_leaf_matches_ethers_vector():
    assert (
        shortfall_leaf(
            42,
            "0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
            "0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC",
            1500,
        )
        == "0x575420915929017ffae0638c52019e8c9e8f744e76c314675af65bb74c76f9f0"
    )
