import base64
import requests
import random
import sys
import math
import re
import json
from datetime import datetime, timedelta

# =============================================================================
# TEMPERATURE-BASED SPEED MODIFIER ADJUSTMENT
# =============================================================================

def getLocalTemperatureAdjustment():
    """Get local temperature and adjust SPEED_MODIFIER based on temperature extremes"""
    try:
        # Load config to get API key
        config = None
        try:
            with open('config.json') as configFile:
                config = json.loads(configFile.read())
        except:
            print("Could not load config.json for temperature check - using default SPEED_MODIFIER")
            return 3
        
        apiKey = config.get('openWeatherAPIKey')
        if not apiKey:
            print("No OpenWeather API key found - using default SPEED_MODIFIER")
            return 3
        
        localZip = "23236"
        baseUrl = "http://api.openweathermap.org/data/2.5/forecast"
        
        params = {
            'zip': f'{localZip},US',
            'units': 'imperial',
            'appid': apiKey
        }

        response = requests.get(baseUrl, params=params)
        
        if response.status_code != 200:
            print(f"Failed to get weather data: {response.text} - using default SPEED_MODIFIER")
            return 3

        forecastData = response.json()
        temperatures = []

        # Get temperatures for next 5 days
        for entry in forecastData['list']:
            temp = entry['main']['temp']
            temperatures.append(temp)

        # Calculate average temperature
        avgTemp = sum(temperatures) / len(temperatures)
        print(f"Local average temperature (5-day forecast): {avgTemp:.1f}°F")
        
        # Calculate adjustment based on temperature extremes
        adjustment = 0
        
        if avgTemp > 70:
            # For every 10 degrees above 70, increase by 1
            degreesAbove = avgTemp - 70
            adjustment = int(degreesAbove / 10)
            print(f"Temperature {avgTemp:.1f}°F is {degreesAbove:.1f}° above 70°F - adding {adjustment} to speed modifier")
        elif avgTemp < 50:
            # For every 10 degrees below 50, increase by 1
            degreesBelow = 50 - avgTemp
            adjustment = int(degreesBelow / 10)
            print(f"Temperature {avgTemp:.1f}°F is {degreesBelow:.1f}° below 50°F - adding {adjustment} to speed modifier")
        else:
            print(f"Temperature {avgTemp:.1f}°F is within normal range (50-70°F) - no adjustment needed")
        
        return adjustment
        
    except Exception as e:
        print(f"Error getting temperature adjustment: {str(e)} - using default SPEED_MODIFIER")
        return 3

# =============================================================================
# CONFIGURATION SETTINGS
# =============================================================================

# Base Speed Modifier: -10 to 10, affects shipping speed preference
# Higher values prefer faster shipping, lower values prefer slower shipping
BASE_SPEED_MODIFIER = 3

# Adjust speed modifier based on local temperature
TEMPERATURE_ADJUSTMENT = getLocalTemperatureAdjustment()
SPEED_MODIFIER = BASE_SPEED_MODIFIER + TEMPERATURE_ADJUSTMENT

# Ensure speed modifier stays within bounds
SPEED_MODIFIER = max(-10, min(10, SPEED_MODIFIER))

print(f"Base Speed Modifier: {BASE_SPEED_MODIFIER}")
print(f"Temperature Adjustment: +{TEMPERATURE_ADJUSTMENT}")
print(f"Final Speed Modifier: {SPEED_MODIFIER}")

# MAX_TRANSIT_DAYS disabled
# MAX_TRANSIT_DAYS = 4

# Order queue threshold for price increases
ORDER_LIMIT = 25

# Weight multiplier for price increases when order queue is high
INCREASE_WEIGHT = 6

# SMALL_ORDER_THRESHOLD disabled
# SMALL_ORDER_THRESHOLD = 10

# Upgrade percentages (base values, will be adjusted by speed modifier)
THREE_DAY_UPGRADE_PERCENTAGE = 20  # Upgrade to 3 Day if cost is less than X% of order
TWO_DAY_UPGRADE_PERCENTAGE = 25    # Upgrade to 2 Day if cost is less than X% of order

# =============================================================================

def loadConfigFromFile():
    """Load API keys and secrets from config.json file"""
    try:
        with open('config.json') as configFile:
            config = json.loads(configFile.read())
            
            return {
                'shipstationAPIKey': config['shipstationAPIKey'],
                'shipstaionAPISecret': config['shipstaionAPISecret'],
                'UPSAuthID': config['UPSAuthID'],
                'UPSAuthPass': config['UPSAuthPass'],
                'openWeatherAPIKey': config['openWeatherAPIKey'],
                'SquarespaceAPIKey': config['SquarespaceAPIKey']
            }
    except FileNotFoundError:
        print("Config file 'config.json' not found")
        return None
    except json.JSONDecodeError as e:
        print(f"Error parsing config file: {str(e)}")
        return None
    except KeyError as e:
        print(f"Missing required key in config file: {str(e)}")
        return None
    except Exception as e:
        print(f"Error reading config file: {str(e)}")
        return None


class ShipstationConnection:
    def __init__(self, shipstationAPIKey, shipstaionAPISecret, UPSAuthID, UPSAuthPass, openWeatherAPIKey):
        self.api_key = shipstationAPIKey
        self.api_secret = shipstaionAPISecret
        self.UPSAuthID = UPSAuthID
        self.UPSAuthPass = UPSAuthPass
        self.openWeatherAPIKey = openWeatherAPIKey
        self.base_url = 'https://ssapi.shipstation.com/'
        self.headers = self._generate_headers()
        self.shipping_service = "usps_ground_advantage"
        self.nonliving = False
        self.expedite = False
        self.ordersInQueue = 0
        
        # Use global speed modifier
        self.speedModifier = max(-10, min(10, SPEED_MODIFIER))
        print(f"Speed Modifier set to: {self.speedModifier}")

    def _generate_headers(self):
        credentials = f"{self.api_key}:{self.api_secret}"
        encoded_credentials = base64.b64encode(credentials.encode('utf-8')).decode('utf-8')
        return {
            'Authorization': f'Basic {encoded_credentials}',
            'Content-Type': 'application/json'
        }

    def get_ups_access_token(self):
        url = "https://wwwcie.ups.com/security/v1/oauth/token"
        payload = {
            "grant_type": "client_credentials",
            "redirect_uri": "https://sunkentreasureaquatics.com",
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        response = requests.post(url, data=payload, headers=headers, auth=(self.UPSAuthID, self.UPSAuthPass))
        if response.status_code == 200:
            return response.json()['access_token']
        else:
            print(f"Failed to get UPS access token: {response.status_code} - {response.text}")
            return None

    def cancel_order(self, order_id):
        print(f"Cancelling order {order_id}...")
        url = f'{self.base_url}orders/{order_id}'
        response = requests.delete(url, headers=self.headers)

        if response.status_code != 200:
            print(f'Failed to cancel order {order_id}: {response.text}')
            return False
        return True

    def get_order_details(self, order_id):
        url = f'{self.base_url}orders/{order_id}'
        response = requests.get(url, headers=self.headers)
        if response.status_code == 200:
            return response.json()
        else:
            print(f'Failed to fetch order {order_id}: {response.text}')
            return None

    def get_product_details(self, sku):
        url = f'{self.base_url}products?sku={sku}'
        response = requests.get(url, headers=self.headers)
        if response.status_code == 200:
            products = response.json()
            if products and 'products' in products and products['products']:
                product = products['products'][0]
                return product
        print(f'Failed to fetch product {sku}: {response.text}')
        return None

    def GetProductTitle(self, sku):
        """
        Get product title by SKU
        
        Args:
            sku (str): The SKU to look up
            
        Returns:
            str: The product title, or None if not found
        """
        product_details = self.get_product_details(sku)
        if product_details:
            return product_details.get('name', None)
        return None

    def UpdateProductInfo(self, sku, updates):
        """
        Update product information by SKU
        
        Args:
            sku (str): The SKU of the product to update
            updates (dict): Dictionary of fields to update
            
        Returns:
            bool: True if successful, False otherwise
        """
        # First get the product to find its ID
        product_details = self.get_product_details(sku)
        if not product_details:
            print(f'Product with SKU {sku} not found')
            return False
        
        # Try different possible ID field names
        product_id = product_details.get('productId') or product_details.get('id')
        if not product_id:
            print(f'Product ID not found for SKU {sku}. Available fields: {list(product_details.keys())}')
            return False
        
        # Create the complete product payload for update
        # ShipStation requires the full product object for updates
        updatePayload = {
            'productId': product_id,
            'sku': product_details.get('sku', sku),
            'name': updates.get('name', product_details.get('name', '')),
            'price': product_details.get('price', 0),
            'defaultCost': product_details.get('defaultCost', 0),
            'length': product_details.get('length', 0),
            'width': product_details.get('width', 0),
            'height': product_details.get('height', 0),
            'weightOz': product_details.get('weightOz', 0),
            'internalNotes': product_details.get('internalNotes', ''),
            'fulfillmentSku': product_details.get('fulfillmentSku', ''),
            'createDate': product_details.get('createDate', ''),
            'modifyDate': product_details.get('modifyDate', ''),
            'active': product_details.get('active', True),
            'productCategory': product_details.get('productCategory', {}),
            'productType': product_details.get('productType', {}),
            'warehouseLocation': product_details.get('warehouseLocation', ''),
            'defaultCarrierCode': product_details.get('defaultCarrierCode', ''),
            'defaultServiceCode': product_details.get('defaultServiceCode', ''),
            'defaultPackageCode': product_details.get('defaultPackageCode', ''),
            'defaultIntlCarrierCode': product_details.get('defaultIntlCarrierCode', ''),
            'defaultIntlServiceCode': product_details.get('defaultIntlServiceCode', ''),
            'defaultIntlPackageCode': product_details.get('defaultIntlPackageCode', ''),
            'defaultConfirmation': product_details.get('defaultConfirmation', ''),
            'defaultIntlConfirmation': product_details.get('defaultIntlConfirmation', ''),
            'customsDescription': product_details.get('customsDescription', ''),
            'customsValue': product_details.get('customsValue', 0),
            'customsTariffNo': product_details.get('customsTariffNo', ''),
            'customsCountryCode': product_details.get('customsCountryCode', ''),
            'noCustoms': product_details.get('noCustoms', False),
            'tags': product_details.get('tags', [])
        }
        
        # Update the product using PUT to specific product endpoint
        url = f'{self.base_url}products/{product_id}'
        response = requests.put(url, headers=self.headers, json=updatePayload)
        
        if response.status_code == 200:
            print(f'Successfully updated product {sku}')
            return True
        else:
            print(f'Failed to update product {sku}: {response.text}')
            return False

    def GetAllProducts(self):
        """
        Get all products from ShipStation
        
        Returns:
            list: List of all products from ShipStation
        """
        print("\nFetching all products from ShipStation...")
        url = f'{self.base_url}products'
        allProducts = []
        page = 1
        pageSize = 500
        
        while True:
            params = {
                'pageSize': pageSize,
                'page': page
            }
            
            response = requests.get(url, headers=self.headers, params=params)
            
            if response.status_code != 200:
                print(f'Failed to fetch products: {response.text}')
                break
                
            data = response.json()
            products = data.get('products', [])
            
            if not products:
                break
                
            allProducts.extend(products)
            print(f"Fetched page {page}: {len(products)} products")
            
            # Check if there are more pages
            if len(products) < pageSize:
                break
                
            page += 1
        
        print(f"Total ShipStation products fetched: {len(allProducts)}")
        return allProducts

    def tag_order(self, order, tag):
        # tag_order disabled for nonliving and USPS
        if tag not in ("expedite",):
            return
        print(f"Adding tag '{tag}' to order {order['orderNumber']}")
        tags = {
            "expedite": "19055"
        }
        url = f'{self.base_url}orders/addtag'
        tag_data = {"orderId": order['orderId'], "tagId": tags[tag]}
        response = requests.post(url, headers=self.headers, json=tag_data)
        if response.status_code != 200:
            print(f'Failed to tag order {order["orderNumber"]}: {response.text}')

    def get_shipping_rates(self, order):
        print(f"Getting shipping rates for {order['orderNumber']} to {order['shipTo']['city']}, {order['shipTo']['state']}")
        url = f'{self.base_url}shipments/getrates'
        
        dimensions = {
                "units": "inches",
                "length": 6.0,
                "width": 4.0,
                "height": 4.0,
                "packageCode": "package"
            }
        
        data = {
            "carrierCode": "ups_walleted",
            "serviceCode": "",
            "packageCode": "",
            "fromPostalCode": '23236',
            "toState": order['shipTo']['state'],
            "toCountry": order['shipTo']['country'],
            "toPostalCode": order['shipTo']['postalCode'],
            "toCity": order['shipTo']['city'],
            "weight": {
                "value": order['weight']['value'],
                "units": order['weight']['units']
            },
            "dimensions": dimensions,
            "confirmation": "delivery",
            "residential": order['shipTo']['residential']
        }
        
        response = requests.post(url, headers=self.headers, json=data)
        if response.status_code == 200:
            return response.json()
        else:
            print(f'Failed to get shipping rates: {response.text}')
            return None

    def get_all_orders(self):
        print("\nFetching awaiting shipment orders...")
        url = f'{self.base_url}orders'
        params = {
            'pageSize': 500,
            'orderStatus': 'awaiting_shipment'
        }
        response = requests.get(url, headers=self.headers, params=params)

        if response.status_code != 200:
            print(f'Failed to fetch orders: {response.text}')
            return []

        orders = response.json().get('orders', [])
        self.ordersInQueue = len(orders)
        print(f"Found {self.ordersInQueue} orders awaiting shipment")
        return orders

    def update_order(self, order_id, order_key, order_number, order_date, order_status, bill_to, ship_to, items, tags, storeId, weight, temp, shipByDays, email, source, requestedShipping, shipping_service=None, notes=None):
        url = f'{self.base_url}orders/createorder'
        ship_by_date = (datetime.strptime(order_date, "%Y-%m-%dT%H:%M:%S.%f000") + timedelta(days=(5 + shipByDays))).strftime('%Y-%m-%d')
        
        isUSPS = bool(shipping_service and shipping_service.startswith("usps_"))
        carrier_code = "stamps_com" if isUSPS else "ups_walleted"
        
        print(f"\nUpdating order {order_number}:")
        print(f"Carrier: {carrier_code}")
        print(f"Service: {shipping_service}")
        print(f"Weight: {weight['value']} {weight['units']}")
        print(f"Ship by: {ship_by_date}")
        if notes:
            print(f"Notes: {notes}")
        
        dimensions = {
            "units": "inches",
            "length": 8.0,
            "width": 6.0,
            "height": 4.0,
            "packageCode": "package"
        }
        
        # Use custom package by ID for USPS
        
        data = {
            "orderKey": order_key,
            "orderNumber": order_number,
            "orderDate": order_date,
            "orderStatus": order_status,
            "billTo": bill_to,
            "shipTo": ship_to,
            "items": items,
            "tagIds": tags,
            "weight": weight,
            "carrierCode": carrier_code,
            "serviceCode": shipping_service,
            "packageCode": "package",
            "requestedShippingService": requestedShipping,
            "customerEmail": email,
            "dimensions": dimensions,
            # no packages array, rely on packageCode ID
            "advancedOptions": {
                "storeId": storeId,
                "customField1": notes if notes else "",
                "customField2": temp,
                "source": source
            },
            "shipByDate": ship_by_date,
        }

        response = requests.post(url, headers=self.headers, json=data)
        
        if response.status_code != 200:
            print(f"Failed to update order: {response.text}")
            return False

        print(f"Successfully updated order {order_number}")
        order_id = response.json().get('orderId')
        return True, order_id

    def is_all_nonliving(self, order):
        if len(order['orderNumber']) > 16 and order['orderNumber'].isupper():
            print("PayPal order detected - not marking as nonliving")
            return False

        print(f"Checking if order {order['orderNumber']} is nonliving...")
        nonliving_items = 0
        total_items_with_sku = 0
        
        for item in order['items']:
            print(f"Checking item: {item.get('name', 'Unknown')} (SKU: {item.get('sku', 'No SKU')})")
            if item['sku']:
                total_items_with_sku += 1
                product_details = self.get_product_details(item['sku'])
                if not product_details:
                    print(f"Could not fetch details for SKU {item['sku']} - assuming not nonliving")
                    return False
                
                print(f"Product details for {item['sku']}: {product_details.get('name', 'Unknown')}")
                categories = product_details.get('productCategory', [])
                print(f"Categories: {categories}")
                
                if isinstance(categories, dict):
                    if "Nonliving" in categories.values():
                        nonliving_items += 1
                        print(f"Item {item['sku']} is nonliving")
                    else:
                        print(f"Categories dict does not contain 'Nonliving' - values: {categories.values()}")
                        return False
                elif isinstance(categories, list):
                    if "Nonliving" in categories:
                        nonliving_items += 1
                        print(f"Item {item['sku']} is nonliving")
                    else:
                        print(f"Categories list does not contain 'Nonliving' - list: {categories}")
                        return False
                else:
                    print(f"Categories is neither dict nor list: {type(categories)}")
                    return False
            else:
                print(f"Skipping item without SKU: {item.get('name', 'Unknown')}")

        # Only mark as nonliving if all items with SKUs are nonliving
        if total_items_with_sku > 0 and nonliving_items == total_items_with_sku:
            print(f"Order contains only nonliving items ({nonliving_items}/{total_items_with_sku} items with SKUs)")
            return True
        else:
            print(f"Order is not all nonliving ({nonliving_items}/{total_items_with_sku} items with SKUs are nonliving)")
            return False

    def remove_nonliving_items(self, order):
        print("Removing nonliving items from order...")
        living_items = []

        for item in order['items']:
            product_details = self.get_product_details(item['sku'])
            if not product_details:
                print(f"Could not fetch details for SKU {item['sku']} - keeping item")
                living_items.append(item)
                continue

            categories = product_details.get('productCategory', [])
            if isinstance(categories, dict):
                if "Nonliving" not in categories.values():
                    living_items.append(item)
            elif isinstance(categories, list):
                if "Nonliving" not in categories:
                    living_items.append(item)
            else:
                living_items.append(item)

        print(f"Kept {len(living_items)} living items")
        return living_items

    def is_replacement_order(self, order):
        if order.get('tagIds', []):
            if 30806 in order.get('tagIds', []):
                print(f"Order {order['orderNumber']} marked as replacement (tag 30806)")
                return True

            if 25911 in order.get('tagIds', []) or 26005 in order.get('tagIds', []):
                print(f"Order {order['orderNumber']} already processed as replacement")
                return False

        if not order['paymentDate']:
            print(f"Order {order['orderNumber']} has no payment date - treating as replacement")
            return True

        payment_date = datetime.strptime(order['paymentDate'], "%Y-%m-%dT%H:%M:%S.%f000")
        order_date = datetime.strptime(order['orderDate'], "%Y-%m-%dT%H:%M:%S.%f000")

        if payment_date < order_date:
            print(f"Order {order['orderNumber']} payment date before order date - marking as replacement")
            return True
        return False

    def get_ups_time_in_transit(self, access_token, origin_zip, destination_zip, weight_lbs):
        shipping_weight = 0.5
        if weight_lbs > 2:
            shipping_weight = 2
        
        print(f"\nChecking UPS transit time from {origin_zip} to {destination_zip} ({shipping_weight}lbs)")
        url = "https://onlinetools.ups.com/api/shipments/v1/transittimes"

        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json',
            'transId': str(random.randint(100000, 9999999999)),
            'transactionSrc': 'testing'
        }

        payload = {
            "originCountryCode": "US",
            "originPostalCode": origin_zip,
            "destinationCountryCode": "US",
            "destinationPostalCode": destination_zip,
            "weight": str(shipping_weight),
            "weightUnitOfMeasure": "LBS",
            "shipDate": datetime.now().strftime("%Y-%m-%d")
        }

        response = requests.post(url, headers=headers, json=payload)

        if response.status_code != 200:
            print(f"Failed to get transit times: {response.status_code} - {response.text}")
            return None

        data = response.json()
        transit_times = {
            'ups_2nd_day_air': None,
            'ups_3_day_select': None,
            'ups_ground': None,
            'ups_ground_saver': None
        }

        services = data.get('emsResponse', {}).get('services', [])
        print("Available transit times:")
        for service in services:
            service_level = service['serviceLevel']
            business_transit_days = int(service['businessTransitDays'])
            
            if service_level == '2DA':
                transit_times['ups_2nd_day_air'] = business_transit_days
                print(f"2nd Day Air: {business_transit_days} days")
            elif service_level == '3DS':
                transit_times['ups_3_day_select'] = business_transit_days
                print(f"3 Day Select: {business_transit_days} days")
            elif service_level == 'GND':
                transit_times['ups_ground'] = business_transit_days
                print(f"Ground: {business_transit_days} days")

        if transit_times['ups_ground']:
            transit_times['ups_ground_saver'] = transit_times['ups_ground'] + 1
            print(f"Ground Saver: {transit_times['ups_ground_saver']} days")

        return transit_times

    def delay_order(self, order_id, delay_days):
        print(f"Delaying order {order_id} by {delay_days} days")
        new_hold_date = (datetime.now() + timedelta(days=delay_days)).strftime('%Y-%m-%dT%H:%M:%S')
        url = f'{self.base_url}orders/holduntil'
        payload = {
            'orderId': order_id,
            'holdUntilDate': new_hold_date
        }
        response = requests.post(url, headers=self.headers, json=payload)

        if response.status_code != 200:
            print(f'Failed to delay order: {response.text}')
            return False

        print(f"Order {order_id} delayed until {new_hold_date}")
        return True

    def get_temperature_high(self, zip_code):
        try:
            print(f"Checking temperature for ZIP: {zip_code}")
            api_key = self.openWeatherAPIKey
            base_url = "http://api.openweathermap.org/data/2.5/forecast"
            
            if "-" in zip_code:
                zip_code = zip_code.split("-")[0]
                print(f"Using ZIP code: {zip_code}")
                
            params = {
                'zip': f'{zip_code},US',
                'units': 'imperial',
                'appid': api_key
            }

            response = requests.get(base_url, params=params)

            if response.status_code != 200:
                print(f"Failed to get weather data: {response.text}")
                return None

            forecast_data = response.json()
            high_temperatures = []

            for entry in forecast_data['list']:
                high_temp = entry['main']['temp_max']
                high_temperatures.append(high_temp)

            average_high = round(sum(high_temperatures) / len(high_temperatures))
            print(f"Average high temperature: {average_high}°F")
            return average_high
        except:  # This is prone to breaking, so if all else fails just return 60
            return 60

    def determine_best_shipping(self, order):
        # USPS only
        requested = order.get('requestedShippingService') or ""
        isExpedite = ("EXPEDITE" in requested) or ("Priority" in requested)

        # normalize dimensions
        if not order.get('dimensions'):
            order['dimensions'] = {}
        order['dimensions']['units'] = 'inches'
        order['dimensions']['length'] = 6.0
        order['dimensions']['width'] = 4.0
        order['dimensions']['height'] = 4.0
        order['dimensions']['packageCode'] = 'package'

        # normalize weight: force all orders to 8 oz
        if isinstance(order.get('weight'), dict):
            order['weight']['units'] = 'ounces'
            order['weight']['value'] = 8

        if isExpedite:
            self.expedite = True
            self.tag_order(order, "expedite")
            return "usps_ground_advantage", "", 60, -5

        return "usps_ground_advantage", "", 60, -2
        origin_zip = "23236"
        destination_zip = order['shipTo']['postalCode']
        
        temperature_high = self.get_temperature_high(destination_zip)
        if temperature_high is None:
            temperature_high = 60
            print(f"Using default temperature: {temperature_high}°F")
        else:
            print(f"Temperature at destination: {temperature_high}°F")
        
        order_total = order['orderTotal']
        current_day = datetime.now().weekday()
        
        # Calculate total weight
        total_weight = 0
        for item in order['items']:
            if isinstance(item.get('weight'), dict):
                weight_value = item['weight'].get('value', 0)
                weight_units = item['weight'].get('units', 'ounces')
                
                if weight_units.lower() == 'ounces':
                    weight_value = weight_value / 16
                
                total_weight += weight_value
                print(f"{item.get('name')}: {weight_value}lbs")
        
        shipping_weight = 0.5
        if total_weight > 2:
            shipping_weight = 2
            print(f"Heavy order - using {shipping_weight}lbs for shipping")
        
        order['weight']['value'] = shipping_weight
        order['weight']['units'] = 'pounds'
        
        # Check for customer-paid services FIRST (before nonliving/small order checks)
        customerPaidForThreeDay = False
        customerPaidForTwoDay = False
        
        if order['requestedShippingService']:
            if "Select" in order['requestedShippingService']:
                customerPaidForThreeDay = True
                print("Customer paid for 3 Day Select - will use 3 Day Select")
            elif "2nd Day" in order['requestedShippingService'] or "Second Day" in order['requestedShippingService']:
                customerPaidForTwoDay = True
                print("Customer paid for 2nd Day Air - will use 2nd Day Air")
            elif "EXPEDITE" in order['requestedShippingService']:
                print("Customer requested expedited shipping - using UPS 2nd Day Air")
                self.expedite = True
                self.tag_order(order, "expedite")
                return "ups_2nd_day_air", "EXPEDITE", temperature_high, -10
        
        # Check for nonliving items (but respect customer-paid services)
        # nonliving logic removed
        
        # Check for small orders (but respect customer-paid services)
        # small order threshold removed

        # Calculate max transit days based on temperature and day of week (IGNORING speed modifier)
        # max transit days removed
        
        # Adjust for extreme temperatures
        # extreme temperature adjustments removed
        
        # Adjust for day of week (reduce max days on weekends)
        # weekend adjustments removed
        
        # Ensure minimum of 2 days
        # final max days removed

        # Get shipping rates and transit times
        rates = self.get_shipping_rates(order)
        if not rates:
            return None, "", temperature_high, -2

        access_token = self.get_ups_access_token()
        if not access_token:
            return None, "", temperature_high, -2

        transit_data = self.get_ups_time_in_transit(access_token, origin_zip, destination_zip, total_weight)
        if not transit_data:
            return None, "", temperature_high, -2

        # Find valid rates within max days
        valid_rates = []
        for rate in rates:
            service_code = rate['serviceCode']
            shipment_cost = rate['shipmentCost']

            if service_code in transit_data and transit_data[service_code] is not None:
                transit_days = transit_data[service_code]
                
                if transit_days <= max_days:
                    valid_rates.append({
                        'serviceCode': service_code,
                        'cost': shipment_cost,
                        'transitDays': transit_days
                    })

        if not valid_rates:
            print("No services found within max transit days - using fastest available")
            # Get all rates and pick the fastest
            all_rates = []
            for rate in rates:
                service_code = rate['serviceCode']
                shipment_cost = rate['shipmentCost']

                if service_code in transit_data and transit_data[service_code] is not None:
                    transit_days = transit_data[service_code]
                    all_rates.append({
                        'serviceCode': service_code,
                        'cost': shipment_cost,
                        'transitDays': transit_days
                    })
            
            if all_rates:
                # Sort by transit days (fastest first)
                all_rates.sort(key=lambda x: x['transitDays'])
                best_rate = all_rates[0]
                print(f"Using fastest available service: {best_rate['serviceCode']} - {best_rate['transitDays']} days")
                return best_rate['serviceCode'], "", temperature_high, -2
            else:
                print("No services found - using UPS 3 Day Select")
                return "ups_3_day_select", "", temperature_high, -2

        # Handle customer-paid services
        if customerPaidForTwoDay:
            # Customer paid for 2nd Day Air - use it
            second_day_rate = None
            for rate in valid_rates:
                if rate['serviceCode'] == 'ups_2nd_day_air':
                    second_day_rate = rate
                    break
            
            if second_day_rate:
                best_rate = second_day_rate
                print(f"Customer paid for 2nd Day Air - using 2nd Day Air: ${best_rate['cost']}")
            else:
                # 2nd Day Air not available, use fastest available
                best_rate = min(valid_rates, key=lambda x: x['transitDays'])
                print(f"2nd Day Air not available - using fastest: {best_rate['serviceCode']} - ${best_rate['cost']}")
        elif customerPaidForThreeDay:
            # Customer paid for 3 Day Select - use it
            three_day_rate = None
            for rate in valid_rates:
                if rate['serviceCode'] == 'ups_3_day_select':
                    three_day_rate = rate
                    break
            
            if three_day_rate:
                best_rate = three_day_rate
                print(f"Customer paid for 3 Day Select - using 3 Day Select: ${best_rate['cost']}")
            else:
                # 3 Day Select not available, use cheapest
                best_rate = min(valid_rates, key=lambda x: x['cost'])
                print(f"3 Day Select not available - using cheapest: {best_rate['serviceCode']} - ${best_rate['cost']}")
        else:
            # No customer-paid service - pick the cheapest service within max days
            best_rate = min(valid_rates, key=lambda x: x['cost'])
            print(f"Selected cheapest service: {best_rate['serviceCode']} - {best_rate['transitDays']} days, ${best_rate['cost']}")

            # Check for 3 Day Select upgrade
            three_day_rate = None
            for rate in valid_rates:
                if rate['serviceCode'] == 'ups_3_day_select':
                    three_day_rate = rate
                    break
            
            if three_day_rate and three_day_rate['serviceCode'] != best_rate['serviceCode']:
                cost_percentage = (three_day_rate['cost'] / float(order_total)) * 100
                
                # Adjust percentage based on speed modifier
                adjusted_percentage = THREE_DAY_UPGRADE_PERCENTAGE + (self.speedModifier * 2)
                
                print(f"3 Day Select cost: ${three_day_rate['cost']:.2f} ({cost_percentage:.1f}% of order, threshold: {adjusted_percentage:.1f}%)")
                
                if cost_percentage <= adjusted_percentage:
                    best_rate = three_day_rate
                    print(f"Upgraded to 3 Day Select - {best_rate['transitDays']} days, ${best_rate['cost']}")

            # Check for 2nd Day Air upgrade
            second_day_rate = None
            for rate in valid_rates:
                if rate['serviceCode'] == 'ups_2nd_day_air':
                    second_day_rate = rate
                    break
            
            if second_day_rate and second_day_rate['serviceCode'] != best_rate['serviceCode']:
                cost_percentage = (second_day_rate['cost'] / float(order_total)) * 100
                
                # Adjust percentage based on speed modifier
                adjusted_percentage = TWO_DAY_UPGRADE_PERCENTAGE + (self.speedModifier * 2)
                
                print(f"2nd Day Air cost: ${second_day_rate['cost']:.2f} ({cost_percentage:.1f}% of order, threshold: {adjusted_percentage:.1f}%)")
                
                if cost_percentage <= adjusted_percentage:
                    best_rate = second_day_rate
                    print(f"Upgraded to 2nd Day Air - {best_rate['transitDays']} days, ${best_rate['cost']}")

        return best_rate['serviceCode'], "", temperature_high, -2

    def run(self):
        orders = self.get_all_orders()

        for order in orders:
            print("\n" + "="*30)
            print(f"ORDER: {order['orderNumber']}")
            print("="*30 + "\n")

            print(f"Items: {len(order['items'])}")
            print(f"Weight: {order['weight']['value']} {order['weight']['units']}")

            tags = order.get('tagIds', [])
            if not tags:
                tags = []
            items = order['items']
            orderKey = order['orderKey']
            orderId = order['orderId']
            orderNumber = order['orderNumber']
            orderDate = order['orderDate']

            selected_service, notes, temp, shipByDays = self.determine_best_shipping(order)

            if selected_service is None:
                print(f"Using default service: {self.shipping_service}")
                selected_service = self.shipping_service

            if self.is_replacement_order(order):
                tags.append(25911)
                if 30806 in tags:
                    tags.remove(30806)
                    print("Removed replacement processing flag")
                
                # # Only remove nonliving items if it's not already a nonliving order
                # if not self.nonliving:
                #     items = self.remove_nonliving_items(order)
                #     if not items:
                #         print("No items remain after removing nonliving items - skipping order")
                #         continue

                self.cancel_order(orderId)
                shipByDays = -5
                orderKey = None
                orderId = None
                orderNumber = f"{orderNumber}-R"
                orderDate = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%S.%f000")
                notes += " [REPLACEMENT]"

            if datetime.strptime(orderDate, "%Y-%m-%dT%H:%M:%S.%f000") + timedelta(days=6) < datetime.now():
                print("Late order!")
                tags.append(31803)
                shipByDays -= 6


            success = self.update_order(
                order_id=orderId,
                order_key=orderKey,
                order_number=orderNumber,
                order_date=orderDate,
                order_status=order['orderStatus'],
                bill_to=order['billTo'],
                ship_to=order['shipTo'],
                items=items,
                tags=tags,
                storeId=order.get('advancedOptions', {}).get('storeId'),
                weight=order['weight'],
                temp=temp,
                source=order.get('advancedOptions', {}).get('source'),
                shipByDays=shipByDays,
                email=order['customerEmail'],
                requestedShipping=order['requestedShippingService'],
                shipping_service=selected_service,
                notes=notes
            )

            if success:
                print(f"\nSuccessfully processed order {orderNumber}")
            else:
                print(f"\nFailed to process order {orderNumber}")

            print("\n" + "="*30)
            print("END OF ORDER")
            print("="*30)

        print("\nOrder processing run completed!")
        return "Done!"


class ProductNaming:
    def __init__(self):
        self.productLocations = {}
        self.sheetUrl = "https://docs.google.com/spreadsheets/d/1kOZ4AVJ0wIYdG1tKaAti60dxfGyAIG4Ol24m29jFgdQ/edit?usp=sharing"
        self.sheetId = "1kOZ4AVJ0wIYdG1tKaAti60dxfGyAIG4Ol24m29jFgdQ"
        
        # Load data from Google Sheets
        self.LoadProductLocations()
    
    def LoadProductLocations(self):
        """
        Column A: SKU
        Column D: Tank #
        """
        try:
            # Use Google Sheets API to get CSV export 
            csvUrl = f"https://docs.google.com/spreadsheets/d/{self.sheetId}/export?format=csv"
            
            response = requests.get(csvUrl)
            response.raise_for_status()
            
            # Parse CSV data
            lines = response.text.strip().split('\n')
            
            # Skip header row and process data
            for i, line in enumerate(lines[1:], start=2):
                try:
                    # Split CSV line 
                    columns = self.ParseCsvLine(line)
                    
                    if len(columns) >= 4:  # Ensure we have at least 4 columns
                        sku = columns[0].strip()  # Column A
                        tankNumber = columns[3].strip()  # Column D
                        
                        # Process tank number
                        if sku and tankNumber:
                            # Extract numbers
                            numbers = re.findall(r'\d+', tankNumber)
                            
                            if numbers:
                                # Join numbers with commas if found
                                processedTank = ", ".join(numbers)
                            else:
                                # Take first word if no numbers
                                processedTank = tankNumber.split()[0]
                            
                            # Only add if tank number isn't empty
                            if processedTank:
                                self.productLocations[sku] = processedTank
                            
                except Exception as e:
                    print(f"Error processing line {i}: {e}")
                    continue
            
            print(f"Successfully loaded {len(self.productLocations)} product locations")
            print(self.productLocations)
            
        except requests.RequestException as e:
            print(f"Error accessing Google Sheets: {e}")
        except Exception as e:
            print(f"Error loading product locations: {e}")
    
    def ParseCsvLine(self, line):
        """
        Parse a CSV line, handling quoted fields that may contain commas
        """
        columns = []
        currentColumn = ""
        inQuotes = False
        
        for char in line:
            if char == '"':
                inQuotes = not inQuotes
            elif char == ',' and not inQuotes:
                columns.append(currentColumn)
                currentColumn = ""
            else:
                currentColumn += char
        
        # Add the last column
        columns.append(currentColumn)
        
        # Clean up quotes from columns
        return [col.strip('"') for col in columns]
    
    def GetTankLocation(self, sku):
        """
        Get the tank location for a given SKU
        
        Args:
            sku (str): The SKU to look up
            
        Returns:
            str: The tank number/location, or None if not found
        """
        return self.productLocations.get(sku)
    
    def GetAllProductLocations(self):
        """
        Get all product locations
        
        Returns:
            dict: Dictionary of SKU -> Tank # mappings
        """
        return self.productLocations.copy()


class Squarespace:
    def __init__(self, shipstation, apikey, productNaming):
        self.shipstation = shipstation
        self.apiKey = apikey
        self.productNaming = productNaming
        self.baseUrl = "https://api.squarespace.com/1.0/"
        self.headers = {
            "Authorization": f"Bearer {self.apiKey}",
            "Content-Type": "application/json"
        }

        self.increaseWeight = INCREASE_WEIGHT
        self.orderLimit = ORDER_LIMIT
        self.lowValueStockLimit = self.orderLimit * 2

        self.basePrices = {
            "plant": 4.99,
            "rare": 7.99,
            "vRare": 11.99,
            "bettaShrimp0": 13.99,
            "bettaShrimp1": 19.99,
            "bundle0": 13.99,
            "bundle1": 19.99,
            "bundle2": 25.99,
            "bundle3": 34.99,
            "clearance0": 9.99,
            "clearance1": 19.99
        }

    def getPlantProducts(self):
        url = f"{self.baseUrl}commerce/products"
        allProducts = []
        hasMore = True
        targetStoreId = "63d6aa29317b5e3016bf0665"
        secondaryStoreId = "63d6ace74d425935bd5cef4d"
        
        print("\nFetching main store products...")
        while hasMore:
            response = requests.get(url, headers=self.headers)
            
            if response.status_code != 200:
                print(f"Error fetching products: {response.status_code} - {response.text}")
                return False
                
            data = response.json()
            products = data.get("products", [])
            
            for product in products:
                tags = product.get("tags", [])
                if (product.get("storePageId") == targetStoreId and "Skip" not in tags):
                    allProducts.append({"product": product, "isSupplyHold": False})

            pagination = data.get("pagination", {})
            hasMore = pagination.get("hasNextPage", False)
            if hasMore:
                url = pagination.get("nextPageUrl", url)

        url = f"{self.baseUrl}commerce/products"
        hasMore = True
        
        print("Fetching supply hold products...")
        while hasMore:
            response = requests.get(url, headers=self.headers)
            
            if response.status_code != 200:
                print(f"Error fetching supply hold products: {response.status_code} - {response.text}")
                return False
                
            data = response.json()
            products = data.get("products", [])
            
            for product in products:
                tags = product.get("tags", [])
                if (product.get("storePageId") == secondaryStoreId and "Skip" not in tags):
                    allProducts.append({"product": product, "isSupplyHold": True})

            pagination = data.get("pagination", {})
            hasMore = pagination.get("hasNextPage", False)
            if hasMore:
                url = pagination.get("nextPageUrl", url)
        
        print(f"Total products found: {len(allProducts)}")
        return allProducts

    def determinePrice(self, product, variantIndex=0):
        productName = product.get("name", "")
        price = 0

        if "bundle" in productName.lower():
            if "betta" in productName.lower() or "shrimp" in productName.lower():
                price = self.basePrices.get(f"bettaShrimp{variantIndex}", self.basePrices["plant"]) 
            elif "clearance" in productName.lower():
                price = self.basePrices.get(f"clearance{variantIndex}", self.basePrices["plant"])
            else:
                price = self.basePrices.get(f"bundle{variantIndex}", self.basePrices["plant"])
        elif "rare" in productName.lower():
            price = self.basePrices["vRare"] if "very" in productName.lower() else self.basePrices["rare"]
        else:
            price = self.basePrices["plant"]

        ordersInQueue = self.shipstation.ordersInQueue
        if ordersInQueue > self.orderLimit:
            basePrice = price
            extraOrders = ordersInQueue - self.orderLimit
            baseIncrease = 0.03 * self.increaseWeight
            
            exponent = 1.5
            increasePercent = baseIncrease * (exponent ** ((extraOrders + 3) / 10))
            increasePercent = min(1.0, increasePercent)
            
            priceIncrease = price * increasePercent
            price += priceIncrease

            print(f"{productName}: ${basePrice:.2f} → ${price:.2f} ({increasePercent:.1%} increase due to {ordersInQueue} orders in queue)")
        else:
            print(f"{productName}: ${price:.2f}")

        return price

    def RoundToNearestDollar99(self, price):
        """
        Round price to nearest $X.99
        Examples: $5.40 -> $4.99, $5.60 -> $5.99, $5.49 -> $4.99, $5.50 -> $5.99
        
        Args:
            price (float): Original price
            
        Returns:
            float: Price rounded to nearest $X.99
        """
        # Get the dollar amount
        dollarAmount = int(price)
        
        # Get the cents portion
        cents = price - dollarAmount
        
        # If cents are 50 or more, round up to next dollar + 0.99
        # If cents are less than 50, round down to current dollar + 0.99
        if cents >= 0.50:
            return dollarAmount + 0.99
        else:
            return max(0.99, dollarAmount - 1 + 0.99) if dollarAmount > 0 else 0.99

    def updateAllPrices(self, products):
        print("\nUpdating product prices...")
        for productData in products:
            product = productData["product"]
            isSupplyHold = productData["isSupplyHold"]
            
            if not isSupplyHold:
                productName = product.get("name", "")
                variants = product.get("variants", [])
                
                for variantIndex, variant in enumerate(variants):
                    updateUrl = f"{self.baseUrl}commerce/products/{product['id']}/variants/{variant['id']}"
                    
                    basePrice = self.determinePrice(product, variantIndex)
                    basePrice = self.RoundToNearestDollar99(basePrice)
                    salePrice = self.RoundToNearestDollar99(basePrice * 0.75)
                    
                    priceData = {
                        "pricing": {
                            "basePrice": {
                                "value": str(basePrice),
                                "currency": "USD"
                            },
                            "salePrice": {
                                "value": str(salePrice),
                                "currency": "USD"
                            }
                        }
                    }
                    
                    response = requests.post(updateUrl, headers=self.headers, json=priceData)
                    if response.status_code != 200:
                        print(f"Failed to update {productName} variant {variantIndex}: {response.text}")
    
    def UpdateShipStationProductNames(self, shipstationProducts):
        """
        Update product names in ShipStation with tank locations
        
        Args:
            shipstationProducts (list): List of product data from ShipStation
        """
        print("\nUpdating ShipStation product names with tank locations...")
        for product in shipstationProducts:
            sku = product.get("sku", "")
            currentName = product.get("name", "")
            
            if sku and currentName:
                # Get tank location from ProductNaming
                tankLocation = self.productNaming.GetTankLocation(sku)
                if tankLocation:
                    # Clean the product name and add tank info
                    baseName = self.CleanProductName(currentName)
                    newName = f"{baseName} [{tankLocation}]"
                    
                    # Only update if the name actually changed
                    if newName != currentName:
                        # Update in ShipStation
                        success = self.shipstation.UpdateProductInfo(sku, {"name": newName})
                        if success:
                            print(f"Updated ShipStation product: '{currentName}' -> '{newName}'")
    
    def CleanProductName(self, productName):
        """
        Clean product name by removing content within brackets and parentheses
        
        Args:
            productName (str): Original product name
            
        Returns:
            str: Cleaned product name
        """
        cleanName = productName
        
        # Remove anything within brackets [content]
        while '[' in cleanName and ']' in cleanName:
            start = cleanName.find('[')
            end = cleanName.find(']', start)
            if start != -1 and end != -1:
                cleanName = cleanName[:start] + cleanName[end+1:]
            else:
                break
        
        # Remove anything within parentheses (content)
        while '(' in cleanName and ')' in cleanName:
            start = cleanName.find('(')
            end = cleanName.find(')', start)
            if start != -1 and end != -1:
                cleanName = cleanName[:start] + cleanName[end+1:]
            else:
                break
        
        # Clean up extra spaces
        cleanName = ' '.join(cleanName.split())
        
        return cleanName.strip()


if __name__ == "__main__":
    # Try to load from config file first
    config = loadConfigFromFile()
    
    if config:
        print("Using config file for API keys")
        shipstationAPIKey = config['shipstationAPIKey']
        shipstaionAPISecret = config['shipstaionAPISecret']
        UPSAuthID = config['UPSAuthID']
        UPSAuthPass = config['UPSAuthPass']
        openWeatherAPIKey = config['openWeatherAPIKey']
        SquarespaceAPIKey = config['SquarespaceAPIKey']
    elif len(sys.argv) >= 7:
        print("Using command line arguments for API keys")
        _, shipstationAPIKey, shipstaionAPISecret, UPSAuthID, UPSAuthPass, openWeatherAPIKey, SquarespaceAPIKey = sys.argv[:7]
    else:
        print("No config file found and insufficient command line arguments provided.")
        print("Please either:")
        print("1. Create a config.json file with your API keys, or")
        print("2. Provide all API keys as command line arguments")
        sys.exit(1)

    # Initialize ProductNaming first to get all product locations
    print("Loading product locations from Google Sheets...")
    productNaming = None
    
    shipstation = ShipstationConnection(shipstationAPIKey, shipstaionAPISecret, UPSAuthID, UPSAuthPass, openWeatherAPIKey)
    sq = Squarespace(shipstation, SquarespaceAPIKey, productNaming)

    # # Run ShipStation order processing
    shipstation.run()
    
    # # Get products from Squarespace (SKUs, Name, Price)
   # plants = sq.getPlantProducts()
    
    # # Update prices to Squarespace
    #sq.updateAllPrices(plants)
    
    # Get products from ShipStation (SKUs, Name)
    #shipstationProducts = shipstation.GetAllProducts()
    
    # Modify product names with tank location and update to ShipStation
    #sq.UpdateShipStationProductNames(shipstationProducts)
