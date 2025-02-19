from flask import Flask, render_template, request
from algosdk.v2client import algod
from algosdk import mnemonic, transaction
import json
import requests
import os
import tempfile
import hashlib
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

##### GLOBAL CONSTANTS ##########
ALGOD_ENDPOINT = os.getenv("ALGOD_ENDPOINT")
API_KEY = os.getenv("API_KEY")
PUBLIC_ADDRESS = os.getenv("PUBLIC_ADDRESS")
MNEMONIC = os.getenv("MNEMONIC")
TOKEN = os.getenv("TOKEN")
HEADERS = {
    "X-Algo-API-Token": API_KEY,
}
PINATA_JWT = os.getenv("PINATA_JWT")
PINATA_KEY = os.getenv("PINATA_KEY")
PINATA_SECRET_KEY = os.getenv("PINATA_SECRET_KEY")
#################################

app = Flask(__name__)
app.secret_key = 'task-1'

# Function to compute SHA-256 hash of a file
def sha256_hash_file(file_path):
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        # Read and update hash string value in blocks of 4K
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

# Function to pin JSON data to IPFS using Pinata
def pin_json(json_):
    url = "https://api.pinata.cloud/pinning/pinJSONToIPFS"
    res = dict()
    res['pinataContent'] = json_
    payload = json.dumps(res)
    headers = {
        'Content-Type': 'application/json',
        'pinata_api_key': PINATA_KEY,
        'pinata_secret_api_key': PINATA_SECRET_KEY
    }

    response = requests.request("POST", url, headers=headers, data=payload)

    return json.loads(response.text)

# Function to pin an image file to IPFS using Pinata
def pin_image(filepath, image_name):
    url = "https://api.pinata.cloud/pinning/pinFileToIPFS"
    payload = {'pinataOptions': '{"cidVersion": 1}',
               'pinataMetadata': '{"name":"'+image_name+'", "keyvalues": {"company": "Pinata"}}'}
    files = [
        ('file', (image_name, open(filepath, 'rb'), 'application/octet-stream'))
    ]
    headers = {
        'pinata_api_key': PINATA_KEY,
        'pinata_secret_api_key': PINATA_SECRET_KEY
    }

    response = requests.request(
        "POST", url, headers=headers, data=payload, files=files)

    return json.loads(response.text)

# Function to create a SHA-256 digest of JSON metadata
def create_digest(json_):
    metadata_json = json.dumps(json_)
    hash_object = hashlib.sha256(metadata_json.encode("utf-8"))
    digest = hash_object.digest()
    return digest.hex()

# Route to render the index page
@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')

# Route to handle NFT creation
@app.route('/', methods=['POST'])
def create_nft():
    asset_name = request.form.get('asset_name')
    unit_name = request.form.get('unit_name')
    description = request.form.get('nft_description')
    prop_data = {}
    for key in request.form:
        if key.startswith('prop[') and key.endswith(']'):
            dynamic_key = key.split('[')[1].split(']')[0]
            prop_data[dynamic_key] = request.form.getlist(key)[0]

    file = request.files['nft_image']
    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        image_mimetype = file.filename.split(".")[-1]
        file.save(temp_file.name)
        res = pin_image(temp_file.name, file.filename)
        image_integrity = sha256_hash_file(temp_file.name)
        temp_file.close()
        os.unlink(temp_file.name)

    if (res['IpfsHash']):
        metadata = dict()
        metadata['name'] = asset_name
        metadata['description'] = description
        metadata['image'] = "ipfs://{}#arc3".format(res['IpfsHash'])
        metadata['image_integrity'] = "sha256-{}".format(image_integrity)
        metadata['image_mimetype'] = "image/{}".format(image_mimetype)
        metadata['properties'] = prop_data
        jsres = pin_json(metadata)
        if (jsres['IpfsHash']):
            digest = create_digest(metadata)
            algod_client = algod.AlgodClient(TOKEN, ALGOD_ENDPOINT, HEADERS)
            nft_mint = transaction.AssetCreateTxn(PUBLIC_ADDRESS, algod_client.suggested_params(
            ), 100, 2, False, unit_name=unit_name, asset_name=asset_name, url="ipfs://"+jsres['IpfsHash']+"#arc3", metadata_hash=bytes.fromhex(digest))
            signed_nft_mint = nft_mint.sign(mnemonic.to_private_key(MNEMONIC))
            tx_id = algod_client.send_transaction(signed_nft_mint)
            results = transaction.wait_for_confirmation(algod_client, tx_id, 4)

            created_asset = results["asset-index"]

            notify = "Created Asset With id : {}".format(str(created_asset))
        else:
            notify = "Failed Uploading MetaData of NFT"
    else:
        notify = "Failed Uploading Image of NFT"

    return render_template('index.html', notify=notify)

if __name__ == '__main__':
    app.run(debug=True)
