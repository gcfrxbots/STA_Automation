import base64
import requests
import random
import sys
import math
from datetime import datetime, timedelta

class ShipstationConnection:
    def __init__(self, shipstationAPIKey, shipstaionAPISecret, UPSAuthID, UPSAuthPass, openWeatherAPIKey):
        self.api_key = shipstationAPIKey
        self.api_secret = shipstaionAPISecret
        self.UPSAuthID = UPSAuthID
        self.UPSAuthPass = UPSAuthPass
        self.openWeatherAPIKey = openWeatherAPIKey
        self.base_url = 'https://ssapi.shipstation.com/'
        self.headers = self._generate_headers()
        self.shipping_service = "ups_ground_saver"
        self.nonliving = False
        self.expedite = False
        self.ordersInQueue = 0

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
                return products['products'][0]
        print(f'Failed to fetch product {sku}: {response.text}')
        return None

    def tag_order(self, order, tag):
        print(f"Adding tag '{tag}' to order {order['orderNumber']}")
        tags = {
            "nonliving": "28635",
            "expedite": "19055",
            "replacement": "25911",
            "impatient": "30832",
            "monthly": "26005",
            "late": "31803",
            "USPS": "38738"
        }
        url = f'{self.base_url}orders/addtag'
        tag_data = {"orderId": order['orderId'], "tagId": tags[tag]}
        response = requests.post(url, headers=self.headers, json=tag_data)
        if response.status_code != 200:
            print(f'Failed to tag order {order["orderNumber"]}: {response.text}')

    def get_shipping_rates(self, order):
        print(f"Getting shipping rates for {order['orderNumber']} to {order['shipTo']['city']}, {order['shipTo']['state']}")
        url = f'{self.base_url}shipments/getrates'
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
            "dimensions": {
                "units": order['dimensions']['units'],
                "length": order['dimensions']['length'],
                "width": order['dimensions']['width'],
                "height": order['dimensions']['height']
            },
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

    def update_order(self, order_id, order_key, order_number, order_date, order_status, bill_to, ship_to, items, tags, storeId, weight, temp, shipByDays, email, source, requestedShipping, custom3, shipping_service=None, notes=None):
        url = f'{self.base_url}orders/createorder'
        ship_by_date = (datetime.strptime(order_date, "%Y-%m-%dT%H:%M:%S.%f000") + timedelta(days=(5 + shipByDays))).strftime('%Y-%m-%d')
        
        carrier_code = "stamps_com" if shipping_service == "usps_ground_advantage" else "ups_walleted"
        custom3 = "USPS & SMALL BOX" if shipping_service == "usps_ground_advantage" else "Standard UPS"
        
        print(f"\nUpdating order {order_number}:")
        print(f"Carrier: {carrier_code}")
        print(f"Service: {shipping_service}")
        print(f"Weight: {weight['value']} {weight['units']}")
        print(f"Ship by: {ship_by_date}")
        if notes:
            print(f"Notes: {notes}")
        
        if shipping_service == "usps_ground_advantage":
            dimensions = {
                "units": "inches",
                "length": 6.0,
                "width": 4.0,
                "height": 4.0,
                "packageCode": "package"
            }
        else:
            dimensions = {
                "units": "inches",
                "length": 8.0,
                "width": 6.0,
                "height": 4.0
            }
        
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
            "packageCode": "package" if shipping_service == "usps_ground_advantage" else None,
            "requestedShippingService": requestedShipping,
            "customereEmail": email,
            "dimensions": dimensions,
            "advancedOptions": {
                "storeId": storeId,
                "customField1": notes if notes else "",
                "customField2": temp,
                "customField3": custom3,
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

        for item in order['items']:
            if item['sku']:
                product_details = self.get_product_details(item['sku'])
                if not product_details:
                    print(f"Could not fetch details for SKU {item['sku']} - assuming not nonliving")
                    return False
                    
                categories = product_details.get('productCategory', [])
                if isinstance(categories, dict):
                    if "Nonliving" not in categories.values():
                        return False
                elif isinstance(categories, list):
                    if "Nonliving" not in categories:
                        return False
                else:
                    return False

        print("Order contains only nonliving items")
        return True

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
            'ups_3_day_select': None,
            'ups_ground': None,
            'ups_ground_saver': None
        }

        services = data.get('emsResponse', {}).get('services', [])
        print("Available transit times:")
        for service in services:
            service_level = service['serviceLevel']
            business_transit_days = int(service['businessTransitDays'])
            
            if service_level == '3DS':
                transit_times['ups_3_day_select'] = business_transit_days
                print(f"3 Day Select: {business_transit_days} days")
            elif service_level == 'GND':
                transit_times['ups_ground'] = business_transit_days
                print(f"Ground: {business_transit_days} days")

        if transit_times['ups_ground']:
            transit_times['ups_ground_saver'] = transit_times['ups_ground'] + 2
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

    def determine_best_shipping(self, order):
        origin_zip = "23236"
        destination_zip = order['shipTo']['postalCode']
        
        temperature_high = self.get_temperature_high(destination_zip)
        if temperature_high is None:
            temperature_high = 60
            print(f"Using default temperature: {temperature_high}°F")
        else:
            print(f"Temperature at destination: {temperature_high}°F")
        
        order_total = order['orderTotal']
        max_days = 2  # Changes the actual max days the box can be in transit
        dayOffset = 0  # Changes the Ship By Date in shipstation
        notes = ""
        current_day = datetime.now().weekday()

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

        # Check temperature and set notes for temperature packs
        if temperature_high > 80:
            notes = "[INCLUDE ICE PACK]"
            print("Adding ice pack")
        elif temperature_high < 40:
            notes = "[INCLUDE HEAT PACK]"
            print("Adding heat pack")

        # Check for expedited shipping first
        if order['requestedShippingService']:
            if "EXPEDITE" in order['requestedShippingService']:
                print("Customer requested expedited shipping - using UPS 2nd Day Air")
                self.expedite = True
                self.tag_order(order, "expedite")
                return "ups_2nd_day_air", "EXPEDITE " + notes, temperature_high, -10

        # Then check for nonliving items
        if self.is_all_nonliving(order):
            self.nonliving = True
            self.tag_order(order, "nonliving")
            
            if total_weight < 1:
                print("Lightweight nonliving - using USPS shipping")
                self.tag_order(order, "USPS")
                order['weight']['value'] = 0.25
                order['weight']['units'] = 'pounds'
                order['dimensions']['packageCode'] = '130843'
                # Early week: delay nonliving (-2 becomes +3)
                if current_day < 3:  # Mon-Wed
                    print("Early week nonliving - low priority")
                    dayOffset = 3
                else:  # Thu-Sun
                    print("Late week nonliving - high priority")
                    dayOffset = -5
                return "usps_ground_advantage", "", temperature_high, dayOffset

            print(f"Heavy nonliving ({total_weight}lbs) - using UPS")
            # Early week: delay nonliving (-2 becomes +3)
            if current_day < 3:  # Mon-Wed
                print("Early week nonliving - low priority")
                dayOffset = 3
            else:  # Thu-Sun
                print("Late week nonliving - high priority")
                dayOffset = -5

            return None, "[NONLIVING - No Perlite]", temperature_high, dayOffset

        # Living plants get priority early in week
        if current_day < 3:  # Mon-Wed
            print("Early week living order - high priority")
            dayOffset = -5
        else:  # Thu-Sun
            print("Late week living order - standard priority")
            dayOffset = -2

        if order.get('tagIds', []):
            if 30832 in order.get('tagIds', []):
                print("Order marked impatient - increasing priority")
                dayOffset = -4

        if temperature_high is None:
            temperature_high = 70

        if temperature_high > 85 or temperature_high < 40:
            max_days -= 1
            print(f"Extreme temperature ({temperature_high}°F) - max transit {max_days} days")

        if order['requestedShippingService']:
            if "Select" in order['requestedShippingService']:
                print("Customer paid for 3 Day Select")
                return "ups_3_day_select", notes, temperature_high, -2

        rates = self.get_shipping_rates(order)
        if not rates:
            return None, notes, temperature_high, dayOffset

        access_token = self.get_ups_access_token()
        if not access_token:
            return None, notes, temperature_high, dayOffset

        transit_data = self.get_ups_time_in_transit(access_token, origin_zip, destination_zip, total_weight)
        if not transit_data:
            return None, notes, temperature_high, dayOffset

        today = datetime.now().date()
        shipping_date = today

        for day in range(1, max_days + 1):
            shipping_day = shipping_date + timedelta(days=day)
            if shipping_day.weekday() == 6:
                max_days -= 1
                print(f"Sunday in transit - adjusted max days to {max_days}")
                break

        best_rate = None

        # Find the cheapest service within max_days constraint
        for rate in rates:
            service_code = rate['serviceCode']
            shipment_cost = rate['shipmentCost']

            if service_code in transit_data and transit_data[service_code] is not None:
                business_transit_days = transit_data[service_code]

                if business_transit_days <= max_days:
                    if best_rate is None or shipment_cost < best_rate['cost']:
                        best_rate = {
                            'serviceCode': rate['serviceCode'],
                            'cost': shipment_cost
                        }

        # Check if the best rate is for UPS 3 Day Select and apply conditions
        if best_rate and best_rate['serviceCode'] == 'ups_3_day_select':
            if best_rate['cost'] > 9 and order_total < 35:
                print(f"Switching to UPS Ground (3 Day Select: ${best_rate['cost']}, order total: ${order_total})")
                for rate in rates:
                    if rate['serviceCode'] == 'ups_ground':
                        best_rate = {
                            'serviceCode': rate['serviceCode'],
                            'cost': rate['shipmentCost']
                        }
                        break
            elif best_rate['cost'] > 11 and order_total < 50:
                print(f"Switching to UPS Ground (3 Day Select: ${best_rate['cost']}, order total: ${order_total})")
                for rate in rates:
                    if rate['serviceCode'] == 'ups_ground':
                        best_rate = {
                            'serviceCode': rate['serviceCode'],
                            'cost': rate['shipmentCost']
                        }
                        break

        if not best_rate:
            print("No valid rate found - using UPS Ground")
            for rate in rates:
                if rate['serviceCode'] == 'ups_ground':
                    best_rate = {
                        'serviceCode': rate['serviceCode'],
                        'cost': rate['shipmentCost']
                    }
                    break

        if best_rate:
            print(f"Selected {best_rate['serviceCode']} at ${best_rate['cost']}")
            return best_rate['serviceCode'], notes, temperature_high, dayOffset

        print("No cheaper services found - using UPS 3 Day Select")
        return "ups_3_day_select", notes, temperature_high, dayOffset

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
                
                # Only remove nonliving items if it's not already a nonliving order
                if not self.nonliving:
                    items = self.remove_nonliving_items(order)
                    if not items:
                        print("No items remain after removing nonliving items - skipping order")
                        continue

                self.cancel_order(orderId)
                shipByDays = -5
                orderKey = None
                orderId = None
                orderNumber = f"{orderNumber}-R"
                orderDate = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%S.%f000")
                notes += " [REPLACEMENT - ADD 3 FREE STEMS]"

            if datetime.strptime(orderDate, "%Y-%m-%dT%H:%M:%S.%f000") + timedelta(days=6) < datetime.now():
                print("Late order!")
                tags.append(31803)
                shipByDays -= 6
                if not self.nonliving:
                    notes += " [ADD 3 FREE STEMS FOR DELAY]"

            multipleItemCount = sum(1 for item in items if item['quantity'] > 1)
            if multipleItemCount > 0:
                multipleItemReminder = f"{multipleItemCount} item{'s' if multipleItemCount > 1 else ''} has multiple quantity"
                print(multipleItemReminder)
            else:
                multipleItemReminder = ""

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
                custom3=multipleItemReminder,
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


class Squarespace:
    def __init__(self, shipstation, apikey):
        self.shipstation = shipstation
        self.apiKey = apikey
        self.baseUrl = "https://api.squarespace.com/1.0/"
        self.headers = {
            "Authorization": f"Bearer {self.apiKey}",
            "Content-Type": "application/json"
        }

        self.increaseWeight = 7  
        self.orderLimit = 20  
        self.lowValueStockLimit = self.orderLimit * 2  

        self.basePrices = {
            "plant": 6.99,
            "rare": 9.99,
            "vRare": 12.99,
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
                    basePrice = math.floor(basePrice) + 0.99
                    salePrice = math.floor(basePrice * 0.75) + 0.99
                    
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


if __name__ == "__main__":
    _, shipstationAPIKey, shipstaionAPISecret, UPSAuthID, UPSAuthPass, openWeatherAPIKey, SquarespaceAPIKey = sys.argv

    shipstation = ShipstationConnection(shipstationAPIKey, shipstaionAPISecret, UPSAuthID, UPSAuthPass, openWeatherAPIKey)
    sq = Squarespace(shipstation, SquarespaceAPIKey)

    shipstation.run()
    plants = sq.getPlantProducts()
    sq.updateAllPrices(plants)

