"""IPFS pin + ERC-721 mint pipeline for Hermes Oracle.

Two entrypoints:
  - `compile_and_deploy()` — one-shot deploy of OracleCard to Base Sepolia.
    Writes the address into .env. Run once.
  - `mint_oracle_card(...)` — pin image + metadata to Pinata, then call
    safeMint on the deployed contract. Called by oracle.py.

CLI:
    python -m nft.mint --deploy
    python -m nft.mint --dry-run   # IPFS only, no on-chain tx
    python -m nft.mint --mint-test --to 0xYourWallet
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import time
from pathlib import Path
from typing import Any

import requests
import solcx
from eth_account import Account
from web3 import Web3

from config import cfg
from ratelimit import record_spend

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent
BUILD_DIR = ROOT / "build"
BUILD_DIR.mkdir(parents=True, exist_ok=True)
SRC = ROOT / "OracleCard.sol"
ARTIFACT = BUILD_DIR / "OracleCard.json"

CHAIN_ID = 84532  # Base Sepolia
COST_PIN_USD = 0.0     # Pinata free tier, treat as zero
COST_GAS_USD_EST = 0.0 # testnet, no real $ — track 0 by default

PINATA_BASE = "https://api.pinata.cloud"
PINATA_GATEWAY = "https://gateway.pinata.cloud/ipfs/"


# ---------- Compile ----------

def compile_contract() -> dict[str, Any]:
    """Compile OracleCard.sol with solcx, cache artifact."""
    if ARTIFACT.exists():
        try:
            return json.loads(ARTIFACT.read_text())
        except Exception:  # noqa: BLE001
            pass

    log.info("installing solc 0.8.24 (one-time)...")
    solcx.install_solc("0.8.24", show_progress=False)
    solcx.set_solc_version("0.8.24")

    src = SRC.read_text()
    compiled = solcx.compile_source(
        src,
        output_values=["abi", "bin", "metadata"],
        optimize=True,
        optimize_runs=200,
        solc_version="0.8.24",
    )
    # Pick the OracleCard contract (key like '<stdin>:OracleCard')
    key = next(k for k in compiled.keys() if k.endswith(":OracleCard"))
    contract = compiled[key]
    artifact = {
        "abi": contract["abi"],
        "bytecode": "0x" + contract["bin"] if not contract["bin"].startswith("0x") else contract["bin"],
    }
    ARTIFACT.write_text(json.dumps(artifact, indent=2))
    return artifact


# ---------- Web3 helpers ----------

def _w3() -> Web3:
    if not cfg.base_sepolia_rpc:
        raise RuntimeError("BASE_SEPOLIA_RPC not set")
    w3 = Web3(Web3.HTTPProvider(cfg.base_sepolia_rpc, request_kwargs={"timeout": 30}))
    if not w3.is_connected():
        raise RuntimeError(f"cannot reach RPC {cfg.base_sepolia_rpc}")
    return w3


def _account() -> Account:
    if not cfg.deployer_private_key:
        raise RuntimeError("DEPLOYER_PRIVATE_KEY not set")
    return Account.from_key(cfg.deployer_private_key)


def _send_tx(w3: Web3, tx: dict[str, Any]) -> dict[str, Any]:
    acct = _account()
    tx.setdefault("from", acct.address)
    tx.setdefault("nonce", w3.eth.get_transaction_count(acct.address))
    tx.setdefault("chainId", CHAIN_ID)
    if "gas" not in tx:
        tx["gas"] = int(w3.eth.estimate_gas(tx) * 1.2)
    if "maxFeePerGas" not in tx:
        base = w3.eth.gas_price
        tx["maxFeePerGas"] = int(base * 2)
        tx["maxPriorityFeePerGas"] = int(min(base, 1_000_000_000))
    signed = acct.sign_transaction(tx)
    raw = signed.raw_transaction
    tx_hash = w3.eth.send_raw_transaction(raw)
    log.info("tx sent: %s", tx_hash.hex())
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
    log.info("tx mined in block %s (status %s)", receipt.blockNumber, receipt.status)
    if receipt.status != 1:
        raise RuntimeError(f"tx reverted: {tx_hash.hex()}")
    return {"tx_hash": tx_hash.hex(), "block": receipt.blockNumber, "receipt": receipt}


# ---------- Deploy ----------

def compile_and_deploy() -> str:
    artifact = compile_contract()
    w3 = _w3()
    acct = _account()

    Contract = w3.eth.contract(abi=artifact["abi"], bytecode=artifact["bytecode"])
    constructor_tx = Contract.constructor("Hermes Oracle Card", "HOC").build_transaction({
        "from": acct.address,
        "nonce": w3.eth.get_transaction_count(acct.address),
        "chainId": CHAIN_ID,
    })
    res = _send_tx(w3, constructor_tx)
    address = res["receipt"].contractAddress
    print(f"Deployed OracleCard at {address}")
    print(f"Etherscan: https://sepolia.basescan.org/address/{address}")
    print(f"Tx:        https://sepolia.basescan.org/tx/{res['tx_hash']}")

    # Patch .env in place — keep all other lines as-is
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        lines = env_path.read_text().splitlines()
        for i, line in enumerate(lines):
            if line.startswith("ORACLE_CARD_CONTRACT="):
                lines[i] = f"ORACLE_CARD_CONTRACT={address}"
                break
        else:
            lines.append(f"ORACLE_CARD_CONTRACT={address}")
        env_path.write_text("\n".join(lines) + "\n")
        print(f"updated .env -> ORACLE_CARD_CONTRACT={address}")
    return address


# ---------- Pinata IPFS ----------

def _pinata_headers() -> dict[str, str]:
    if not cfg.pinata_jwt:
        raise RuntimeError("PINATA_JWT not set")
    return {"Authorization": f"Bearer {cfg.pinata_jwt}"}


def pin_file(path: Path, name: str | None = None) -> str:
    files = {"file": (name or path.name, path.read_bytes())}
    metadata = json.dumps({"name": name or path.name})
    r = requests.post(
        f"{PINATA_BASE}/pinning/pinFileToIPFS",
        files=files,
        data={"pinataMetadata": metadata},
        headers=_pinata_headers(),
        timeout=60,
    )
    r.raise_for_status()
    cid = r.json()["IpfsHash"]
    record_spend(COST_PIN_USD, "pinata")
    return cid


def pin_json(data: dict[str, Any], name: str) -> str:
    payload = {
        "pinataContent": data,
        "pinataMetadata": {"name": name},
    }
    r = requests.post(
        f"{PINATA_BASE}/pinning/pinJSONToIPFS",
        json=payload,
        headers={**_pinata_headers(), "Content-Type": "application/json"},
        timeout=30,
    )
    r.raise_for_status()
    cid = r.json()["IpfsHash"]
    record_spend(COST_PIN_USD, "pinata")
    return cid


def build_metadata(card: dict[str, Any], question: str, interpretation_excerpt: str,
                   reading_id: str, image_cid: str) -> dict[str, Any]:
    return {
        "name": f"Mnemos — {card['name']}{' (Reversed)' if card.get('reversed') else ''}",
        "description": (
            f"A card from a Mnemos reading. Question: \"{question}\".\n\n"
            f"{interpretation_excerpt}\n\n"
            f"Mnemos is a Hermes Agent skill (Nous Research) interpreted by Kimi K2.6 "
            f"(Moonshot AI). For reflection, not prescription."
        ),
        "image": f"ipfs://{image_cid}",
        "external_url": "https://github.com/dream0x/Mnemos",
        "attributes": [
            {"trait_type": "Card", "value": card["name"]},
            {"trait_type": "Arcana", "value": card.get("arcana", "minor")},
            {"trait_type": "Position", "value": card.get("position", "single")},
            {"trait_type": "Orientation", "value": "Reversed" if card.get("reversed") else "Upright"},
            {"trait_type": "Reading ID", "value": reading_id},
        ],
    }


# ---------- Mint ----------

def mint_oracle_card(
    *,
    recipient: str,
    card: dict[str, Any],
    question: str,
    interpretation_excerpt: str,
    reading_id: str,
) -> dict[str, Any]:
    """Pin image+metadata to IPFS, then safeMint on the deployed OracleCard."""
    if not cfg.oracle_card_contract or cfg.oracle_card_contract.lower() == "0x" + "0" * 40:
        raise RuntimeError("ORACLE_CARD_CONTRACT not set — run `python -m nft.mint --deploy` first")

    image_path = Path(card["image_path"])
    if not image_path.exists():
        raise RuntimeError(f"missing image {image_path}")

    image_cid = pin_file(image_path, name=f"hermes-oracle-{card['id']}.png")
    metadata = build_metadata(card, question, interpretation_excerpt, reading_id, image_cid)
    metadata_cid = pin_json(metadata, name=f"hermes-oracle-{reading_id}-{card['id']}.json")
    token_uri = f"ipfs://{metadata_cid}"

    w3 = _w3()
    artifact = compile_contract()
    contract = w3.eth.contract(address=Web3.to_checksum_address(cfg.oracle_card_contract), abi=artifact["abi"])
    acct = _account()

    fn = contract.functions.safeMint(Web3.to_checksum_address(recipient), token_uri)
    tx = fn.build_transaction({
        "from": acct.address,
        "nonce": w3.eth.get_transaction_count(acct.address),
        "chainId": CHAIN_ID,
    })
    res = _send_tx(w3, tx)

    # Decode CardMinted event for tokenId
    receipt = res["receipt"]
    token_id: int | None = None
    for log_ in receipt.logs:
        try:
            ev = contract.events.CardMinted().process_log(log_)
            token_id = int(ev["args"]["tokenId"])
            break
        except Exception:
            continue
    if token_id is None:
        # fallback: totalSupply() reads as the latest minted id since we 1-index sequentially
        token_id = int(contract.functions.totalSupply().call())

    contract_lower = cfg.oracle_card_contract.lower()
    viewer = (
        f"{cfg.viewer_base_url}?contract={contract_lower}&token={token_id}"
        if cfg.viewer_base_url else
        f"https://sepolia.basescan.org/token/{contract_lower}?a={token_id}"
    )
    out = {
        "token_id": token_id,
        "tx_hash": res["tx_hash"],
        "tx_url": f"https://sepolia.basescan.org/tx/{res['tx_hash']}",
        "viewer_url": viewer,
        "basescan_token_url": f"https://sepolia.basescan.org/token/{contract_lower}?a={token_id}",
        "metadata_uri": token_uri,
        "image_cid": image_cid,
        "metadata_cid": metadata_cid,
    }
    log.info("minted #%s -> %s", token_id, out["viewer_url"])
    return out


# ---------- CLI ----------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("--compile", action="store_true", help="compile only")
    p.add_argument("--deploy", action="store_true", help="compile + deploy to Base Sepolia")
    p.add_argument("--dry-run", action="store_true", help="pin demo image+metadata, no on-chain tx")
    p.add_argument("--mint-test", action="store_true", help="full pin + mint cycle using a cached card")
    p.add_argument("--to", type=str, help="recipient address (defaults to deployer)")
    args = p.parse_args()

    if args.compile:
        a = compile_contract()
        print(f"compiled OK; abi={len(a['abi'])} entries; bytecode {len(a['bytecode'])//2-1} bytes")

    if args.deploy:
        compile_and_deploy()

    if args.dry_run:
        # Pin one cached card image + a fake metadata; no chain tx.
        from tarot import deck as deck_mod
        from tarot.render import _cache_key
        card_id = "the-fool"
        card = {
            "id": card_id,
            "name": deck_mod.by_id(card_id).name,
            "arcana": "major",
            "position": "single",
            "reversed": False,
            "image_path": str(_cache_key(card_id, False)),
        }
        cid = pin_file(Path(card["image_path"]))
        meta = build_metadata(card, "Test pin", "Sample interpretation excerpt.", "dryrun01", cid)
        meta_cid = pin_json(meta, "dryrun.json")
        print(f"image cid = {cid}")
        print(f"meta  cid = {meta_cid}")
        print(f"image gw  = {PINATA_GATEWAY}{cid}")
        print(f"meta  gw  = {PINATA_GATEWAY}{meta_cid}")

    if args.mint_test:
        from tarot import deck as deck_mod
        from tarot.render import _cache_key
        card_id = "the-fool"
        card = {
            "id": card_id,
            "name": deck_mod.by_id(card_id).name,
            "arcana": "major",
            "position": "single",
            "reversed": False,
            "image_path": str(_cache_key(card_id, False)),
        }
        recipient = args.to or _account().address
        result = mint_oracle_card(
            recipient=recipient,
            card=card,
            question="Test mint from CLI",
            interpretation_excerpt="The Fool steps off the cliff, white dog at heel.",
            reading_id="testreading01",
        )
        print(json.dumps(result, indent=2))
