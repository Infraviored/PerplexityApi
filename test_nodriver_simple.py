#!/usr/bin/env python3
"""
Minimal nodriver test - using nodriver's own event loop
Tests both headless and headed modes
"""
import asyncio
import nodriver as uc
import time
import sys


async def test_headless():
    """Test nodriver in headless mode"""
    print("=" * 60)
    print("Testing NODRIVER - HEADLESS MODE")
    print("=" * 60)
    
    try:
        print("\n1. Starting browser (headless=True, sandbox=False)...")
        browser = await asyncio.wait_for(
            uc.start(headless=True, sandbox=False),
            timeout=30
        )
        print("   ✓ Browser started!")
        
        print("\n2. Getting main tab...")
        page = browser.main_tab
        print("   ✓ Main tab obtained!")
        
        print("\n3. Navigating to Google...")
        await asyncio.wait_for(
            page.get("https://www.google.com"),
            timeout=30
        )
        print("   ✓ Navigation successful!")
        
        print(f"\n4. Page title: {page.title}")
        print(f"   URL: {page.url}")
        
        print("\n5. Testing element selection...")
        search_box = await page.select("textarea[name='q']", timeout=10)
        if search_box:
            print("   ✓ Found search box!")
        else:
            print("   ✗ Search box not found")
        
        print("\n6. Stopping browser...")
        try:
            # browser.stop() might not be async or might return None
            stop_result = browser.stop()
            if stop_result and asyncio.iscoroutine(stop_result):
                await stop_result
            print("   ✓ Browser stopped!")
        except Exception as e:
            print(f"   ⚠ Browser stop note: {e}")
            # Browser will be cleaned up automatically
        
        print("\n✅ HEADLESS MODE TEST PASSED!")
        return True
        
    except asyncio.TimeoutError:
        print("\n❌ TIMEOUT - Browser operation took too long")
        return False
    except Exception as e:
        print(f"\n❌ ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_headed():
    """Test nodriver in headed (visible) mode"""
    print("\n" + "=" * 60)
    print("Testing NODRIVER - HEADED MODE")
    print("=" * 60)
    
    try:
        print("\n1. Starting browser (headless=False, sandbox=False)...")
        browser = await asyncio.wait_for(
            uc.start(headless=False, sandbox=False),
            timeout=30
        )
        print("   ✓ Browser started!")
        
        print("\n2. Getting main tab...")
        page = browser.main_tab
        print("   ✓ Main tab obtained!")
        
        print("\n3. Navigating to Google...")
        await asyncio.wait_for(
            page.get("https://www.google.com"),
            timeout=30
        )
        print("   ✓ Navigation successful!")
        
        print(f"\n4. Page title: {page.title}")
        print(f"   URL: {page.url}")
        
        print("\n5. Testing element selection...")
        search_box = await page.select("textarea[name='q']", timeout=10)
        if search_box:
            print("   ✓ Found search box!")
        else:
            print("   ✗ Search box not found")
        
        print("\n6. Stopping browser...")
        try:
            # browser.stop() might not be async or might return None
            stop_result = browser.stop()
            if stop_result and asyncio.iscoroutine(stop_result):
                await stop_result
            print("   ✓ Browser stopped!")
        except Exception as e:
            print(f"   ⚠ Browser stop note: {e}")
            # Browser will be cleaned up automatically
        
        print("\n✅ HEADED MODE TEST PASSED!")
        return True
        
    except asyncio.TimeoutError:
        print("\n❌ TIMEOUT - Browser operation took too long")
        return False
    except Exception as e:
        print(f"\n❌ ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_perplexity():
    """Test navigating to Perplexity.ai"""
    print("\n" + "=" * 60)
    print("Testing NODRIVER - PERPLEXITY.AI")
    print("=" * 60)
    
    try:
        print("\n1. Starting browser (headless=True, sandbox=False)...")
        browser = await asyncio.wait_for(
            uc.start(headless=True, sandbox=False),
            timeout=30
        )
        print("   ✓ Browser started!")
        
        print("\n2. Getting main tab...")
        page = browser.main_tab
        print("   ✓ Main tab obtained!")
        
        print("\n3. Navigating to Perplexity.ai...")
        await asyncio.wait_for(
            page.get("https://www.perplexity.ai"),
            timeout=30
        )
        print("   ✓ Navigation successful!")
        
        print(f"\n4. Page title: {page.title}")
        print(f"   URL: {page.url}")
        
        print("\n5. Waiting for page to load...")
        await asyncio.sleep(3)
        
        print("\n6. Testing element selection (question input)...")
        # Try to find the question input
        question_input = await page.select("p[dir='auto']", timeout=10)
        if question_input:
            print("   ✓ Found question input!")
        else:
            print("   ✗ Question input not found (might need login)")
        
        print("\n7. Stopping browser...")
        try:
            # Try async stop first
            if hasattr(browser, 'stop') and callable(browser.stop):
                result = browser.stop()
                if asyncio.iscoroutine(result):
                    await result
            print("   ✓ Browser stopped!")
        except Exception as e:
            print(f"   ⚠ Browser stop warning: {e}")
            # Browser will be cleaned up automatically
        
        print("\n✅ PERPLEXITY TEST PASSED!")
        return True
        
    except asyncio.TimeoutError:
        print("\n❌ TIMEOUT - Browser operation took too long")
        return False
    except Exception as e:
        print(f"\n❌ ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run tests"""
    print("NODRIVER MINIMAL TEST")
    print("=" * 60)
    print("This will test nodriver with its own event loop")
    print("Using: uc.loop().run_until_complete()")
    print("=" * 60)
    
    # Get nodriver's event loop
    loop = uc.loop()
    
    # Ask user which test to run
    if len(sys.argv) > 1:
        test_mode = sys.argv[1].lower()
    else:
        print("\nWhich test to run?")
        print("1. headless - Test headless mode")
        print("2. headed - Test headed (visible) mode")
        print("3. perplexity - Test Perplexity.ai navigation")
        print("4. all - Run all tests")
        test_mode = input("\nEnter choice (1-4): ").strip()
    
    results = {}
    
    if test_mode in ['1', 'headless']:
        results['headless'] = loop.run_until_complete(test_headless())
    elif test_mode in ['2', 'headed']:
        results['headed'] = loop.run_until_complete(test_headed())
    elif test_mode in ['3', 'perplexity']:
        results['perplexity'] = loop.run_until_complete(test_perplexity())
    elif test_mode in ['4', 'all']:
        results['headless'] = loop.run_until_complete(test_headless())
        time.sleep(2)
        results['headed'] = loop.run_until_complete(test_headed())
        time.sleep(2)
        results['perplexity'] = loop.run_until_complete(test_perplexity())
    else:
        print("Invalid choice. Running headless test by default...")
        results['headless'] = loop.run_until_complete(test_headless())
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    for test_name, result in results.items():
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{test_name.upper()}: {status}")
    
    # Return exit code
    all_passed = all(results.values()) if results else False
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()

