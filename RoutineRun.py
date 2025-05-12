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
        self.shipping_service = "ups_ground_saver"  # Default shipping service code
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
            access_token = response.json()['access_token']
            return access_token
        else:
            print(f"Failed to retrieve access token: {response.status_code} - {response.text}")
            return None

    def cancel_order(self, order_id):
        url = f'{self.base_url}orders/{order_id}'
        response = requests.delete(url, headers=self.headers)

        if response.status_code != 200:
            print(f'Error canceling order {order_id}:', response.text)
            return False

        return True

    def get_order_details(self, order_id):
        url = f'{self.base_url}orders/{order_id}'
        response = requests.get(url, headers=self.headers)
        if response.status_code == 200:
            return response.json()
        else:
            print(f'Error fetching order details: {response.text}')
            return None

    def get_product_details(self, sku):
        url = f'{self.base_url}products?sku={sku}'
        response = requests.get(url, headers=self.headers)
        if response.status_code == 200:
            products = response.json()
            if products and 'products' in products and products['products']:
                return products['products'][0]  # Assuming SKU is unique, fetch the first match
        print(f'Error fetching product details for SKU {sku}: {response.text}')
        return None

    def tag_order(self, order, tag):
        tags = {
            "nonliving": "28635",
            "expedite": "19055",
            "replacement": "25911",
            "impatient": "30832",
            "monthly": "26005",  # Shouldnt be needed but adding just to keep track of it
            "late": "31803",
            "USPS": "38738"
        }
        url = f'{self.base_url}orders/addtag'
        tag_data = {"orderId": order['orderId'], "tagId": tags[tag]}
        response = requests.post(url, headers=self.headers, json=tag_data)
        if response.status_code == 200:
            print(f'Order {order["orderNumber"]} tagged successfully.')
        else:
            print(f'Error tagging order {order["orderNumber"]}: {response.text}')

    def get_shipping_rates(self, order):
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
            print(f'Error fetching shipping rates: {response.text}')
            return None

    def get_all_orders(self):
        url = f'{self.base_url}orders'
        params = {
            'pageSize': 500,
            'orderStatus': 'awaiting_shipment'
        }
        response = requests.get(url, headers=self.headers, params=params)

        #print(requests.get(f'{self.base_url}carriers', headers=self.headers).json())

        if response.status_code != 200:
            print('Error fetching orders:', response.text)
            return []

        orders = response.json().get('orders', [])
        self.ordersInQueue = len(orders) # Track order count
        return orders

    def update_order(self, order_id, order_key, order_number, order_date, order_status, bill_to, ship_to, items, tags, storeId, weight, temp, shipByDays, email, source, requestedShipping, custom3, shipping_service=None, notes=None):
        url = f'{self.base_url}orders/createorder'
        ship_by_date = (datetime.strptime(order_date, "%Y-%m-%dT%H:%M:%S.%f000") + timedelta(days=(5 + shipByDays))).strftime('%Y-%m-%d')
        
        # Determine carrier code based on shipping service
        carrier_code = "stamps_com" if shipping_service == "usps_ground_advantage" else "ups_walleted"
        
        # Set custom3 based on shipping service
        custom3 = "USPS" if shipping_service == "usps_ground_advantage" else "Standard UPS"
        
        # Debug prints
        print(f"\nDEBUG - Update Order Details:")
        print(f"Order Number: {order_number}")
        print(f"Shipping Service: {shipping_service}")
        print(f"Carrier Code: {carrier_code}")
        print(f"Weight: {weight['value']} {weight['units']}")
        
        # Set dimensions based on shipping service
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
        
        print(f"Package Code: {dimensions.get('packageCode', 'Not set')}")
        
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

        print("FINAL DATA")
        print(data)
        response = requests.post(url, headers=self.headers, json=data)
        
        # Debug response
        print(f"DEBUG - API Response: {response.status_code}")
        if response.status_code != 200:
            print(f"DEBUG - Error response: {response.text}")

        if response.status_code != 200:
            print(f'Error updating order {order_id}:', response.text)
            return False

        order_id = response.json().get('orderId')

        return True, order_id

    def is_all_nonliving(self, order):
        """
        Determines if all items in an order are categorized as 'Nonliving'.
        """
        nonliving_category = "Nonliving"
        all_nonliving = True

        if len(order['orderNumber']) > 16 and order['orderNumber'].isupper():
            print("Order is a paypal order, not marking as nonliving")
            return False

        for item in order['items']:
            if item['sku']:  # Skip any item missing a sku
                product_details = self.get_product_details(item['sku'])
                if not product_details:
                    all_nonliving = False
                    print(f"Could not fetch product details for SKU {item['sku']}, assuming not all nonliving.")
                    break
                categories = product_details.get('productCategory', [])
                if isinstance(categories, dict):
                    if "Nonliving" not in categories.values():
                        all_nonliving = False
                        break
                elif isinstance(categories, list):
                    if "Nonliving" not in categories:
                        all_nonliving = False
                        break
                else:
                    all_nonliving = False
                    break

        return all_nonliving

    def remove_nonliving_items(self, order):
        nonliving_category = "Nonliving"
        living_items = []

        for item in order['items']:
            product_details = self.get_product_details(item['sku'])
            if not product_details:
                print(f"Could not fetch product details for SKU {item['sku']}, assuming living item.")
                living_items.append(item)  # Assume item is living if details are unavailable
                continue

            categories = product_details.get('productCategory', [])
            if isinstance(categories, dict):
                if nonliving_category not in categories.values():
                    living_items.append(item)  # Add item if it's not nonliving
            elif isinstance(categories, list):
                if nonliving_category not in categories:
                    living_items.append(item)
            else:
                living_items.append(item)  # Default to assuming the item is living if categorization is unknown

        return living_items

    def is_replacement_order(self, order):

        if order.get('tagIds', []):
            if 30806 in order.get('tagIds', []):
                return True

            if 25911 in order.get('tagIds', []) or 26005 in order.get('tagIds', []):  # Checks if REPLACEMENT or MONTHLY BOX tag is present.
                return False  # Prevents code from recreating replacements

        # Check if paymentDate is earlier than orderDate
        if not order['paymentDate']:
            return True

        payment_date = datetime.strptime(order['paymentDate'], "%Y-%m-%dT%H:%M:%S.%f000")
        order_date = datetime.strptime(order['orderDate'], "%Y-%m-%dT%H:%M:%S.%f000")

        # Logic to determine if it's a replacement order
        if payment_date < order_date:
            return True
        return False

    def get_ups_time_in_transit(self, access_token, origin_zip, destination_zip, weight_lbs):
        """
        Function to call UPS Time in Transit API with the provided access token,
        origin and destination ZIP codes, and package weight.
        Returns a dictionary with the number of transit days for specific UPS services.
        """
        url = "https://onlinetools.ups.com/api/shipments/v1/transittimes"

        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json',
            'transId': str(random.randint(100000, 9999999999)),
            'transactionSrc': 'testing'
        }

        # UPS Time in Transit request payload, trimmed down to essential fields
        payload = {
            "originCountryCode": "US",  # Origin country code
            "originPostalCode": origin_zip,  # Origin postal code
            "destinationCountryCode": "US",  # Destination country code
            "destinationPostalCode": destination_zip,  # Destination postal code
            "weight": str(weight_lbs),  # Weight of the package in lbs
            "weightUnitOfMeasure": "LBS",  # Unit of measurement for weight
            "shipDate": datetime.now().strftime("%Y-%m-%d")  # Shipping date in YYYY-MM-DD format
        }

        response = requests.post(url, headers=headers, json=payload)

        if response.status_code != 200:
            print(f"Error fetching Time in Transit data: {response.status_code} - {response.text}")
            return None

        data = response.json()

        # Initialize the dictionary for storing the transit days
        transit_times = {
            'ups_3_day_select': None,
            'ups_ground': None,
            'ups_ground_saver': None
        }

        # Extract available services
        services = data.get('emsResponse', {}).get('services', [])

        # Loop through the services and map them to the appropriate keys
        for service in services:
            service_level = service['serviceLevel']
            business_transit_days = int(service['businessTransitDays'])

            # Match the service level codes with the required ones
            if service_level == '3DS':  # UPS 3 Day Select
                transit_times['ups_3_day_select'] = business_transit_days
            elif service_level == 'GND':  # UPS Ground
                transit_times['ups_ground'] = business_transit_days

        # If UPS Ground Saver is not provided, default to UPS Ground + 1
        transit_times['ups_ground_saver'] = transit_times['ups_ground'] + 1 if transit_times['ups_ground'] else None

        return transit_times

    def delay_order(self, order_id, delay_days):
        new_hold_date = (datetime.now() + timedelta(days=delay_days)).strftime('%Y-%m-%dT%H:%M:%S')
        url = f'{self.base_url}orders/holduntil'
        payload = {
            'orderId': order_id,
            'holdUntilDate': new_hold_date
        }
        response = requests.post(url, headers=self.headers, json=payload)

        if response.status_code != 200:
            print(f'Error delaying order {order_id}:', response.text)
            return False

        print(f"Order {order_id} delayed until {new_hold_date}.")
        return True

    def get_temperature_high(self, zip_code):
        """
        Retrieves the average high temperature for the next 7 days for the given ZIP code
        using the OpenWeatherMap API.
        """
        api_key = self.openWeatherAPIKey # Replace with your OpenWeatherMap API key
        base_url = "http://api.openweathermap.org/data/2.5/forecast"
        if "-" in zip_code:
            zip_code = zip_code.split("-")[0]
        params = {
            'zip': f'{zip_code},US',  # Assuming US ZIP codes, adjust the country if needed
            'units': 'imperial',  # Fahrenheit
            'appid': api_key
        }

        response = requests.get(base_url, params=params)

        if response.status_code != 200:
            print(f"Error fetching weather data for ZIP {zip_code}: {response.text}")
            return None

        forecast_data = response.json()
        high_temperatures = []

        # Collect daily high temperatures for the next 7 days
        for entry in forecast_data['list']:
            # 'list' contains multiple entries per day, we filter for the daily high temperatures
            high_temp = entry['main']['temp_max']
            high_temperatures.append(high_temp)

        # Average the temperatures over the next 7 days
        average_high = round(sum(high_temperatures) / len(high_temperatures))
        return average_high

    def determine_best_shipping(self, order):
        self.nonliving = False
        self.expedite = False
        origin_zip = "23236"
        destination_zip = order['shipTo']['postalCode']
        temperature_high = self.get_temperature_high(destination_zip)
        order_total = order['orderTotal']
        max_days = 4
        dayOffset = 0

        print(f"\nDEBUG - Processing order {order['orderNumber']}")

        # Calculate actual total weight from items
        total_weight = 0
        for item in order['items']:
            if isinstance(item.get('weight'), dict):
                weight_value = item['weight'].get('value', 0)
                weight_units = item['weight'].get('units', 'ounces')
                
                # Convert to pounds if in ounces
                if weight_units.lower() == 'ounces':
                    weight_value = weight_value / 16
                
                print(f"DEBUG - Item weight: {weight_value} pounds")    
                total_weight += weight_value
        
        print(f"DEBUG - Total weight: {total_weight} pounds")
        
        # Set default weight to 8oz (0.5 lbs)
        order['weight']['value'] = 0.5
        order['weight']['units'] = 'pounds'

        # Check for nonliving orders
        if self.is_all_nonliving(order):
            self.nonliving = True
            self.tag_order(order, "nonliving")
            print(f"DEBUG - Order is nonliving")
            
            if total_weight < 1:
                print(f"DEBUG - Lightweight nonliving order - using USPS shipping")
                print(f"DEBUG - Setting weight to 4oz and package type to 130843")
                self.tag_order(order, "USPS")
                
                # Update order weight to 4oz
                order['weight']['value'] = 0.25
                order['weight']['units'] = 'pounds'
                
                # Update package type
                order['dimensions']['packageCode'] = '130843'
                
                return "usps_ground_advantage", "[NONLIVING - No Perlite]", temperature_high, dayOffset

            print(f"DEBUG - Nonliving order too heavy for USPS: {total_weight} pounds")
            # Original nonliving logic for heavier items
            current_day = datetime.now().weekday()
            if current_day >= 3:
                print("DEBUG - Late week nonliving, prioritizing")
                dayOffset = -4
            else:
                print("DEBUG - Early week nonliving, delaying")
                dayOffset = 1

            return None, "[NONLIVING - No Perlite]", temperature_high, dayOffset

        if order.get('tagIds', []):
            if 30832 in order.get('tagIds', []):  # Prioritize orders for customers who are asking about their order status
                print("Prioritizing order with Impatient tag")
                dayOffset = -4

        if temperature_high is None:
            print(f"Unable to determine temperature for ZIP {destination_zip}.")
            temperature_high = 70  # Assume neutral temperature if API call fails.

        # Adjust delivery days based on temperature
        if temperature_high > 85 or temperature_high < 40:
            max_days = 3  # Stricter limit for extreme temperatures
            print(f"Temperature high is {temperature_high}, setting max delivery days to {max_days}")

        # Notes for ice/heat pack
        notes = ""
        if temperature_high > 85:
            notes = "[INCLUDE ICE PACK]"
        elif temperature_high < 40:
            notes = "[INCLUDE HEAT PACK]"

        # Step 0: Adjust dayOffset based on the current day of the week for nonliving orders
        current_day = datetime.now().weekday()  # Monday is 0, Sunday is 6
        if self.is_all_nonliving(order):
            self.nonliving = True
            self.tag_order(order, "nonliving")

            if current_day >= 3:  # If the day is thursday or later, prioritize nonlivings.
                print("NONLIVING - It's late in the week, prioritizing")
                dayOffset = -4
            else:
                print("NONLIVING - Early in the week, delaying til later")
                dayOffset = 1

            return None, "[NONLIVING - No Perlite]", temperature_high, dayOffset  # Prioritize based on the day of the week

        if order['requestedShippingService']:
            if "EXPEDITE" in order['requestedShippingService']:
                print("Order is expedited")
                self.expedite = True
                self.tag_order(order, "expedite")
                return "ups_2nd_day_air", "EXPEDITE " + notes, temperature_high, -10

            if "Select" in order['requestedShippingService']:
                print("Customer paid for 3 Day Select")
                return "ups_3_day_select", notes, temperature_high, -2


        # Step 1: Get shipping rates
        rates = self.get_shipping_rates(order)
        if not rates:
            print("Failed to retrieve shipping rates.")
            return None, notes, temperature_high, dayOffset

        # Step 2: Get the OAuth access token
        access_token = self.get_ups_access_token()
        if not access_token:
            print("Failed to retrieve UPS OAuth access token.")
            return None, notes, temperature_high, dayOffset

        # Step 3: Get time in transit data once
        transit_data = self.get_ups_time_in_transit(access_token, origin_zip, destination_zip, total_weight)

        if not transit_data:
            print("Failed to retrieve Time in Transit data.")
            return None, notes, temperature_high, dayOffset

        # Step to account for Sundays
        today = datetime.now().date()  # Current date
        shipping_date = today  # Assume shipping starts today

        # Check if Sunday falls within the max_days window
        for day in range(1, max_days + 1):
            shipping_day = shipping_date + timedelta(days=day)
            if shipping_day.weekday() == 6:  # Sunday is weekday 6
                max_days -= 1  # Subtract 1 day from max_days if a Sunday falls within the window
                print("Sunday detected in shipping window, adjusting max days to:", max_days)
                break  # Only adjust once for a Sunday

        best_rate = None

        # Step 4: Find the cheapest service within max_days constraint
        for rate in rates:
            service_code = rate['serviceCode']  # This matches the key from transit_data
            shipment_cost = rate['shipmentCost']

            # Check if there's a matching service with valid transit days
            if service_code in transit_data and transit_data[service_code] is not None:
                business_transit_days = transit_data[service_code]

                # Ensure the service meets the max_days constraint
                if business_transit_days <= max_days:
                    if best_rate is None or shipment_cost < best_rate['cost']:
                        best_rate = {
                            'serviceCode': rate['serviceCode'],
                            'cost': shipment_cost
                        }

        # Check if the best rate is for UPS 3 Day Select and apply the condition
        if best_rate and best_rate['serviceCode'] == 'ups_3_day_select':
            if best_rate['cost'] > 9 and order_total < 35:
                print(f"Switching to UPS Ground because UPS 3 Day Select rate is {best_rate['cost']} and order total is {order_total}")
                # Find the UPS Ground rate and use it
                for rate in rates:
                    if rate['serviceCode'] == 'ups_ground':
                        best_rate = {
                            'serviceCode': rate['serviceCode'],
                            'cost': rate['shipmentCost']
                        }
                        break
            elif best_rate['cost'] > 11 and order_total < 50:
                print(f"Switching to UPS Ground because UPS 3 Day Select rate is {best_rate['cost']} and order total is {order_total}")
                # Find the UPS Ground rate and use it
                for rate in rates:
                    if rate['serviceCode'] == 'ups_ground':
                        best_rate = {
                            'serviceCode': rate['serviceCode'],
                            'cost': rate['shipmentCost']
                        }
                        break

        # If no valid rate was found, default to UPS 3 Day Select but still apply the cost checks
        if not best_rate:
            print("No valid rate found, defaulting to UPS Ground")
            for rate in rates:
                if rate['serviceCode'] == 'ups_ground':
                    best_rate = {
                        'serviceCode': rate['serviceCode'],
                        'cost': rate['shipmentCost']
                    }
                    break

            # Apply the cost check for UPS 3 Day Select
            if best_rate and best_rate['serviceCode'] == 'ups_3_day_select':
                if best_rate['cost'] > 11 and order_total < 35:
                    print(f"Switching to UPS Ground because UPS 3 Day Select rate is {best_rate['cost']} and order total is {order_total}")
                    for rate in rates:
                        if rate['serviceCode'] == 'ups_ground':
                            best_rate = {
                                'serviceCode': rate['serviceCode'],
                                'cost': rate['shipmentCost']
                            }
                            break
                elif best_rate['cost'] > 12.5 and order_total < 50:
                    print(f"Switching to UPS Ground because UPS 3 Day Select rate is {best_rate['cost']} and order total is {order_total}")
                    for rate in rates:
                        if rate['serviceCode'] == 'ups_ground':
                            best_rate = {
                                'serviceCode': rate['serviceCode'],
                                'cost': rate['shipmentCost']
                            }
                            break

        # Return the best rate if found, otherwise return the default UPS 3 Day Select
        if best_rate:
            return best_rate['serviceCode'], notes, temperature_high, dayOffset

        # If all else fails, default to UPS 3 Day Select
        print("No cheaper services found, defaulting to UPS 3 Day Select.")
        return "ups_3_day_select", notes, temperature_high, dayOffset

    def run(self):
        orders = self.get_all_orders()
        subscriptions = Subscriptions(self)

        for order in orders:
            print(
                f"\nChecking order: {order['orderNumber']} - Status: {order['orderStatus']} - Items: {len(order['items'])} - Weight: {order['weight']['value']}")

            # Process subscription orders first
            subscription_processed = subscriptions.process_subscription_orders(order)

            if subscription_processed:
                print(
                    f"Processed subscription order {order['orderNumber']}. Proceeding with regular order updates for the original order.")
                continue


            # Continue with regular order processing, including for the modified original order
            tags = order.get('tagIds', [])
            if not tags:
                tags = []
            items = order['items']
            orderKey = order['orderKey']
            orderId = order['orderId']
            orderNumber = order['orderNumber']
            orderDate = order['orderDate']

            # Determine the best shipping service and any special notes based on temperature
            selected_service, notes, temp, shipByDays = self.determine_best_shipping(order)

            if selected_service is None:
                selected_service = self.shipping_service  # Use default if not specified

            # Check REPLACEMENTS
            if self.is_replacement_order(order):
                print(f"Order {orderNumber} is a replacement - Processing accordingly.")
                tags.append(25911)
                if 30806 in tags:  # Remove the flag to process the order as a replacement
                    tags.remove(30806)
                items = self.remove_nonliving_items(order)
                if not items:
                    print("NO ITEMS IN ORDER - JUST SKIPPING IT!")
                    continue

                self.cancel_order(orderId)
                shipByDays = -5
                orderKey = None
                orderId = None
                orderNumber = f"{orderNumber}-R"
                orderDate = (datetime.now() - timedelta(days=5)).strftime(
                    "%Y-%m-%dT%H:%M:%S.%f000")  # Sets it as if the order was placed 5 days ago to prioritize the replacements.
                notes += " [REPLACEMENT - ADD 3 FREE STEMS]"

            # CHECK IF ORDER IS LATE
            if datetime.strptime(orderDate, "%Y-%m-%dT%H:%M:%S.%f000") + timedelta(days=6) < datetime.now():
                print("Order is late! Prioritizing and tagging late!")
                tags.append(31803)  # LATE tag
                shipByDays -= 4
                if not self.nonliving:
                    notes += " [ADD 3 FREE STEMS FOR DELAY]"  # Only add free stems if they bought other plants

            # Add a reminder if there is stuff with more than 1 quantity
            multipleItemReminder = ""
            multipleItemCount = sum(1 for item in items if item['quantity'] > 1)
            if multipleItemCount == 1:
                multipleItemReminder = f"Note: {multipleItemCount} item has a quantity of 2 or more!"
            if multipleItemCount > 1:
                multipleItemReminder = f"Note: {multipleItemCount} items have a quantity of 2 or more!"

            # Update the order with the selected shipping service and any notes
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
                shipping_service=selected_service,  # Pass the selected shipping service
                notes=notes  # Pass any notes such as "Include Ice Pack" or "Include Heat Pack"
            )

            if success:
                print(f"Order {order['orderNumber']} updated with shipping service: {selected_service} \n")
            else:
                print(f"Failed to update shipping service for order {order['orderNumber']}")

        return "Done!"


class Subscriptions:
    def __init__(self, shipstation_connection):
        self.shipstation = shipstation_connection
        self.subscription_skus = ["SUB3", "SUB6", "SUB9", "SUB12"]

    def process_subscription_orders(self, order):
        subscription_item = self._find_subscription_item(order['items'])
        if subscription_item:
            months = int(subscription_item['sku'].replace('SUB', ''))

            # Update the original order: remove subscription item and add "SUBBUNDLE"
            original_items = [item for item in order['items'] if item['sku'] not in self.subscription_skus]
            original_items.append({
                "sku": "SUBBUNDLE",
                "name": "Subscription Bundle",
                "quantity": 1,
                "unitPrice": 0.00
            })

            tags = order.get('tagIds', [])
            if tags is None:
                tags = []
            tags.append(26005)  # Add the subscription tag to the original order

            # Update the original order in Shipstation
            update_success = self.shipstation.update_order(
                order_id=order['orderId'],
                order_key=order['orderKey'],
                order_number=order['orderNumber'],
                order_date=order['orderDate'],
                order_status=order['orderStatus'],
                bill_to=order['billTo'],
                ship_to=order['shipTo'],
                items=original_items,
                tags=tags,
                storeId=order.get('advancedOptions', {}).get('storeId'),
                weight=order['weight'],
                temp="",
                source=order.get('advancedOptions', {}).get('source'),
                shipByDays=0,
                custom3="",
                email=order['customerEmail'],
                requestedShipping=order['requestedShippingService'],
                shipping_service=self.shipstation.shipping_service,  # Default shipping service
                notes=""  # No special notes
            )

            if not update_success:
                print(f"Failed to update the original order {order['orderNumber']}.")
                return False

            print(f"Original order {order['orderNumber']} updated successfully with subscription changes.")

            # Create subsequent orders for each month
            for month in range(2, months+1):
                delay_days = (month - 1) * 30
                sub_order_number = f"{order['orderNumber']}-SUB-{month}"
                order_date = datetime.now().strftime('%Y-%m-%dT%H:%M:%S.%f000')
                sub_items = [
                    {
                        "sku": "SUBBUNDLE",
                        "name": "Subscription Bundle",
                        "quantity": 1,
                        "unitPrice": 0.00
                    }
                ]

                # Create the new order for the subscription month
                success, order_id = self.shipstation.update_order(
                    order_id=None,  # No existing order ID since this is a new order
                    order_key=None,
                    order_number=sub_order_number,
                    order_date=order_date,
                    order_status=order['orderStatus'],
                    bill_to=order['billTo'],
                    ship_to=order['shipTo'],
                    items=sub_items,
                    tags=[26005],  # Tagging the new order as part of the subscription
                    storeId=order.get('advancedOptions', {}).get('storeId'),
                    weight=order['weight'],
                    temp="",
                    source=order.get('advancedOptions', {}).get('source'),
                    shipByDays=delay_days - 5,  # 30 / 60 / 90 / etc days - 5 for the built in offset
                    custom3="",
                    email=order['customerEmail'],
                    requestedShipping=order['requestedShippingService'],
                    shipping_service=self.shipstation.shipping_service,  # Default shipping service
                    notes=""  # No special notes
                )

                if not success:
                    print(f"Failed to create order {sub_order_number}.")
                    continue

                # Delay the new orders as required
                if month > 1:
                    self.shipstation.delay_order(order_id=order_id, delay_days=delay_days)

            return True

        return False

    def _find_subscription_item(self, items):
        for item in items:
            if item['sku'] in self.subscription_skus:
                return item
        return None


class Squarespace:
    def __init__(self, shipstation, apikey):
        self.shipstation = shipstation
        # Connect to Squarespace API
        self.apiKey = apikey
        self.baseUrl = "https://api.squarespace.com/1.0/"
        self.headers = {
            "Authorization": f"Bearer {self.apiKey}",
            "Content-Type": "application/json"
        }

        self.increaseWeight = 7  # 1 to 10, 10 is the most intensive increase in price.

        self.orderLimit = 20  # Number of orders to have in the queue before increasing price.
        self.lowValueStockLimit = self.orderLimit * 2  # 2x order limit threshold

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
        # Get all products with pagination
        url = f"{self.baseUrl}commerce/products"
        products = []
        offset = 0
        pageSize = 50
        # Get all products 
        allProducts = []
        hasMore = True
        targetStoreId = "63d6aa29317b5e3016bf0665"
        secondaryStoreId = "63d6ace74d425935bd5cef4d"
        
        # First get main store products
        while hasMore:
            response = requests.get(url, headers=self.headers)
            
            if response.status_code != 200:
                print("Error fetching products:", response.text)
                return False
                
            data = response.json()
            products = data.get("products", [])
            
            # Filter products that shouldn't be processed
            for product in products:
                tags = product.get("tags", [])
                
                if (product.get("storePageId") == targetStoreId and 
                    "Skip" not in tags):
                    allProducts.append({"product": product, "isSupplyHold": False})

            # Check pagination
            pagination = data.get("pagination", {})
            hasMore = pagination.get("hasNextPage", False)
            if hasMore:
                nextUrl = pagination.get("nextPageUrl")
                if nextUrl:
                    url = nextUrl
                else:
                    hasMore = False

        # Reset for supply hold products
        url = f"{self.baseUrl}commerce/products"
        hasMore = True
        
        # Now get supply hold products
        while hasMore:
            response = requests.get(url, headers=self.headers)
            
            if response.status_code != 200:
                print("Error fetching products:", response.text)
                return False
                
            data = response.json()
            products = data.get("products", [])
            
            # Filter supply hold products
            for product in products:
                tags = product.get("tags", [])
                
                if (product.get("storePageId") == secondaryStoreId and 
                    "Skip" not in tags):
                    allProducts.append({"product": product, "isSupplyHold": True})

            # Check pagination
            pagination = data.get("pagination", {})
            hasMore = pagination.get("hasNextPage", False)
            if hasMore:
                nextUrl = pagination.get("nextPageUrl")
                if nextUrl:
                    url = nextUrl
                else:
                    hasMore = False
        
        print(f"Found {len(allProducts)} total products")
        return allProducts

    def determinePrice(self, product, variantIndex=0):
        # Get name
        productName = product.get("name", "").lower()
        price = 0

        # Check bundle type
        if "bundle" in productName:
            if "betta" in productName or "shrimp" in productName:
                price = self.basePrices.get(f"bettaShrimp{variantIndex}", self.basePrices["plant"]) 
            elif "clearance" in productName:
                price = self.basePrices.get(f"clearance{variantIndex}", self.basePrices["plant"])
            else:
                price = self.basePrices.get(f"bundle{variantIndex}", self.basePrices["plant"])
        
        # Check rarity 
        elif "rare" in productName:
            price = self.basePrices["vRare"] if "very" in productName else self.basePrices["rare"]
        
        # Default price
        else:
            price = self.basePrices["plant"]


        # Now calculate the price increase

        # Get order queue count
        ordersInQueue = self.shipstation.ordersInQueue
        # Price increase over 20 orders
        if ordersInQueue > self.orderLimit:
            basePrice = price
            # Calculate increase based on queue size
            extraOrders = ordersInQueue - self.orderLimit
            baseIncrease = 0.03 * self.increaseWeight
            
            # Exponential increase
            exponent = 1.5
            increasePercent = baseIncrease * (exponent ** ((extraOrders + 3) / 10))
            
            # Cap at 100% increase
            increasePercent = min(1.0, increasePercent)
            
            # Apply increase
            priceIncrease = price * increasePercent
            price += priceIncrease

            print(f"Base price: ${basePrice:.2f}, Increased by {increasePercent:.1%}, New price: ${(price):.2f}")
        else:
            print("Base price:" + str(price) + " - No increase")

        return price

    def updateAllPrices(self, products):
        for productData in products:
            product = productData["product"]
            isSupplyHold = productData["isSupplyHold"]
            
            productName = product.get("name", "")
            variants = product.get("variants", [])
            tags = product.get("tags", [])
            
            for variantIndex, variant in enumerate(variants):
                if isSupplyHold:
                    # Only update stock for supply hold products
                    stockUrl = f"{self.baseUrl}commerce/inventory/adjustments"
                    stockLevel = 0 if self.shipstation.ordersInQueue > self.lowValueStockLimit else 500
                    
                    stockData = {
                        "setFiniteOperations": [{
                            "variantId": variant['id'],
                            "quantity": stockLevel
                        }]
                    }
                    
                    stockHeaders = self.headers.copy()
                    stockHeaders["Idempotency-Key"] = f"stock_update_{variant['id']}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
                    
                    stockResponse = requests.post(stockUrl, headers=stockHeaders, json=stockData)
                    
                    if stockResponse.status_code not in [204, 200]:
                        print(f"Error updating stock for supply hold {productName} variant {variantIndex}: {stockResponse.text}")
                    else:
                        print(f"Updated supply hold {productName} variant {variantIndex} stock to {stockLevel}\n")
                    
                else:
                    # Regular price and stock updates for main store products
                    updateUrl = f"{self.baseUrl}commerce/products/{product['id']}/variants/{variant['id']}"
                    priceData = {}
                    isLowValue = "lowval" in tags
                    
                    # Calculate prices for all products
                    basePrice = self.determinePrice(product, variantIndex)
                    basePrice = math.floor(basePrice) + 0.99
                    salePrice = math.floor(basePrice * 0.75) + 0.99
                    
                    priceData["pricing"] = {
                        "basePrice": {
                            "value": str(basePrice),
                            "currency": "USD"
                        },
                        "salePrice": {
                            "value": str(salePrice),
                            "currency": "USD"
                        }
                    }
                    priceMsg = f"${basePrice} (sale: ${salePrice})"
                    
                    # Update prices
                    response = requests.post(updateUrl, headers=self.headers, json=priceData)
                    if response.status_code != 200:
                        print(f"Error updating prices for {productName} variant {variantIndex}: {response.text}")
                        continue
                    
                    # Handle stock updates for low value items
                    if isLowValue:
                        stockLevel = 0 if self.shipstation.ordersInQueue > self.lowValueStockLimit else 900
                        stockUrl = f"{self.baseUrl}commerce/inventory/adjustments"
                        
                        stockData = {
                            "setFiniteOperations": [{
                                "variantId": variant['id'],
                                "quantity": stockLevel
                            }]
                        }
                        
                        stockHeaders = self.headers.copy()
                        stockHeaders["Idempotency-Key"] = f"stock_update_{variant['id']}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
                        
                        stockResponse = requests.post(stockUrl, headers=stockHeaders, json=stockData)
                        
                        if stockResponse.status_code not in [204, 200]:
                            print(f"Error updating stock for {productName} variant {variantIndex}: {stockResponse.text}")
                            stockMsg = ", Stock update failed"
                        else:
                            stockMsg = f", Stock: {stockLevel}"
                    else:
                        stockMsg = ""
                    
                    print(f"Updated {productName} variant {variantIndex} to {priceMsg}{stockMsg}\n")




if __name__ == "__main__":
    # Extract the arguments
    _, shipstationAPIKey, shipstaionAPISecret, UPSAuthID, UPSAuthPass, openWeatherAPIKey, SquarespaceAPIKey= sys.argv

    shipstation = ShipstationConnection(shipstationAPIKey, shipstaionAPISecret, UPSAuthID, UPSAuthPass, openWeatherAPIKey)
    sq = Squarespace(shipstation, SquarespaceAPIKey)
    #sq = Squarespace()


    shipstation.run()
    plants = sq.getPlantProducts()
    sq.updateAllPrices(plants)
    #sq.rollbackPlantPrices(plants)

