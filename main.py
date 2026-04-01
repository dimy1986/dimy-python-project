import sys
from voucher_extractor import extract_vouchers
from voucher_validator import validate_vouchers


def main():
    # Example entry point to run voucher extraction and validation
    try:
        vouchers = extract_vouchers()  # Assuming it returns a list of vouchers
        valid_vouchers = validate_vouchers(vouchers)  # Validate the extracted vouchers
        print(f"Valid vouchers: {valid_vouchers}")
    except Exception as e:
        print(f"An error occurred: {e}")


if __name__ == '__main__':
    main()