#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test script for Prediction Module

This script demonstrates the prediction module functionality
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_imports():
    """Test that all modules can be imported"""
    print("Testing imports...")
    
    try:
        from prediction import PredictionWidget, PredictionLogic
        print("✅ Imports successful")
        print(f"   - PredictionWidget: {PredictionWidget}")
        print(f"   - PredictionLogic: {PredictionLogic}")
        return True
    except Exception as e:
        print(f"❌ Import failed: {e}")
        return False


def test_logic():
    """Test prediction logic"""
    print("\nTesting prediction logic...")
    
    try:
        from prediction import PredictionLogic
        
        logic = PredictionLogic()
        print("✅ PredictionLogic initialized")
        
        # Check attributes
        assert logic.model is None
        assert logic.model_type is None
        assert logic.lookback == 60
        print("✅ Default attributes correct")
        
        return True
    except Exception as e:
        print(f"❌ Logic test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_widget():
    """Test prediction widget (without Qt)"""
    print("\nTesting widget structure...")
    
    try:
        from prediction.ui import widget_prediction
        
        # Check class exists
        assert hasattr(widget_prediction, 'PredictionWidget')
        assert hasattr(widget_prediction, 'TrainingThread')
        print("✅ Widget classes found")
        
        # Check methods
        methods = dir(widget_prediction.PredictionWidget)
        required_methods = [
            'on_train_model',
            'on_predict',
            'on_backtest',
            'on_save_model',
            'on_load_model',
            'update_metrics',
            'update_chart'
        ]
        
        for method in required_methods:
            assert method in methods, f"Missing method: {method}"
        print("✅ All required methods present")
        
        return True
    except Exception as e:
        print(f"❌ Widget test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_ui_file():
    """Test UI file structure"""
    print("\nTesting UI file...")
    
    try:
        import xml.etree.ElementTree as ET
        
        ui_path = Path(__file__).parent.parent / "ui" / "prediction" / "prediction.ui"
        tree = ET.parse(ui_path)
        root = tree.getroot()
        
        # Check widget class
        widget_class = root.find(".//class")
        assert widget_class.text == "PredictionWidget"
        print("✅ Widget class correct")
        
        # Check required widgets
        required_widgets = [
            'combo_model',
            'combo_data_source',
            'combo_period',
            'btn_train',
            'btn_predict',
            'btn_backtest',
            'btn_save_model',
            'btn_load_model',
            'progress_bar',
            'table_metrics',
            'widget_chart',
            'text_log'
        ]
        
        found_widgets = set()
        for widget in root.findall('.//widget'):
            name = widget.get('name')
            if name:
                found_widgets.add(name)
        
        for widget_name in required_widgets:
            assert widget_name in found_widgets, f"Missing widget: {widget_name}"
        print("✅ All required widgets present")
        
        return True
    except Exception as e:
        print(f"❌ UI file test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests"""
    print("=" * 60)
    print("Prediction Module Test Suite")
    print("=" * 60)
    
    results = []
    
    # Run tests
    results.append(("Imports", test_imports()))
    results.append(("Logic", test_logic()))
    results.append(("Widget", test_widget()))
    results.append(("UI File", test_ui_file()))
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{test_name:20s}: {status}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n✅ All tests passed!")
        return 0
    else:
        print(f"\n❌ {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
