from src.client_library.client_exception import ClientException
from .exceptions import ProductNotFound
from src.client_library.ozon.OzonClient import OzonClient
import traceback

class OzonAdapter:
    ozon_token: str
    client: OzonClient

    def __init__(self, ozon_token):
        self.ozon_token = ozon_token
        parts = ozon_token.split(':')
        client_id, api_key = parts if len(parts) == 2 else ['dummy', 'dummy']
        self.client = OzonClient(client_id, api_key)
    
    async def get_product_data(self, sku):
        try:
            response = self.client.get_products_info({
                'offer_id': sku,
            })
        except Exception as e:
            raise ProductNotFound()
        return response['result']

    async def get_product_description(self, sku):
        try:
            response = self.client.get_products_description({
                'offer_id': sku,
            })
        except Exception as e:
            raise ProductNotFound()
        return response['result']
    
    async def test_token(self):
        try:
            response = self.client.get_products({
                "last_id": "",
                "limit": 1
            })
        except Exception:
            return False
        return True
    
    async def set_video_preview(self, sku, video_url):
        product_data = self.client.get_product_attributes(sku)['result'][0]
        product_attributes = self.client.get_product_attributes(sku)['result'][0]['attributes']
        attributes = self.client.get_attributes(product_data['category_id'])['result'][0]['attributes']

        # print('product_attributes', product_attributes)

        cover_attribute_id = None
        for attribute in attributes:
            if 'Видеообложка' in attribute['name']:
                cover_attribute_id = attribute['id']
                # print('attribute', attribute)


        # for i in range(len(product_attributes)):
        #     if product_attributes[i]['attribute_id'] == cover_attribute_id:
        #         del product_attributes[i]
        #     else:
        #         product_attributes[i]['id'] = product_attributes[i]['attribute_id']
        #         del product_attributes[i]['attribute_id']
        product_attributes = [{
            'id': cover_attribute_id,
            'values': [
                {
                    'value': video_url
                }
            ]
        }]

        try:
            response = self.client.update_product_attributes(sku, product_attributes)
            print('task_id', response)
        except ClientException as e:
            print(f"An unexpected error occurred: {e}")
            print(f"Traceback: {traceback.format_exc()}")
            return {'is_success': False, 'error': e.data['message']}
        return {'is_success': True}
