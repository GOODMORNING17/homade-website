from django.http import HttpResponse, JsonResponse, HttpResponseNotFound
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from .models import *
from django.db.models import Sum
from django.contrib.auth.models import User
from .utils import menu_to_dict
from django.forms import ModelForm, modelformset_factory

# Create your views here.


def index(request):
    basque_burnt_cheesecakes = MenuItem.objects.filter(meal__meal_type__name="Basque Burnt Cheesecake").values("meal__name", "price")
    madeleines = menu_to_dict(MenuItem.objects.filter(meal__meal_type__name="Madeleine").values("meal__name", "price"))

    context = {
        "basque_burnt_cheesecakes": basque_burnt_cheesecakes,
        "madeleines": madeleines
    }
    if request.user.is_authenticated:
        context["cart_items_count"] = Cart.objects.filter(user=request.user).count()
    return render(request, "orders/index.html", context)


def order(request):
    basque_burnt_cheesecakes = MenuItem.objects.filter(meal__meal_type__name="Basque Burnt Cheesecake")
    madeleines = MenuItem.objects.filter(meal__meal_type__name="Madeleine")

    context = {
        "basque_burnt_cheesecakes": basque_burnt_cheesecakes,
        "madeleines": madeleines
    }
    return render(request, "orders/order.html", context)


@require_POST
def add_to_cart(request):
    form = request.POST
    user_id = request.user.id
    menu_item_id = form.get('menu_item_id', None)
    toppings = form.get('toppings_list', None)
    toppings_list = list()
    sub_additions = form.get('sub_additions_list', None)
    sub_additions_list = list()
    if user_id is None or menu_item_id is None:
        return JsonResponse({'success': False, 'message': 'No user or menu item.'}, status=400)
    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        return JsonResponse({'success': False, 'message': "User doesn't exist."}, status=400)
    try:
        menu_item = MenuItem.objects.get(pk=menu_item_id)
    except MenuItem.DoesNotExist:
        return JsonResponse({'success': False, 'message': "Menu item doesn't exist."}, status=400)
    if toppings:
        toppings_list = toppings.split(",")
    if menu_item.toppings_count and menu_item.toppings_count != len(toppings_list):
        return JsonResponse({'success': False, 'message': 'Invalid toppings count.'}, status=400)
    if sub_additions:
        sub_additions_list = sub_additions.split(",")
    item = Cart()
    item.user = user
    item.menu_item = menu_item
    item.price = menu_item.price
    item.save()
    for i in toppings_list:
        try:
            topping = Topping.objects.get(pk=i)
        except Topping.DoesNotExist:
            return JsonResponse({'success': False, 'message': "Topping doesn't exist."}, status=400)
        item.toppings.add(topping)
    for i in sub_additions_list:
        try:
            sub_addition = SubAddition.objects.get(pk=i)
        except SubAddition.DoesNotExist:
            return JsonResponse({'success': False, 'message': "Sub addition doesn't exist."}, status=400)
        item.sub_additions.add(sub_addition)
        item.price += sub_addition.price
    item.save()
    cart_items_count = Cart.objects.filter(user=user).count()
    return JsonResponse({'success': True, 'message': 'Item added to cart.', 'cart_items_count': cart_items_count, 'item': str(menu_item)}, status=200)


@login_required(login_url="users:login")
def cart(request):
    form = request.POST
    if form:
        item_id = form.get('remove_item', None)
        if item_id:
            try:
                cart_item = Cart.objects.get(pk=item_id)
                cart_item.delete()
            except Cart.DoesNotExist:
                pass

    context = {
        "cart_items_count": Cart.objects.filter(user=request.user).count(),
        "cart_items": Cart.objects.filter(user=request.user),
        "cart_cost": Cart.objects.filter(user=request.user).aggregate(Sum('price')),
        "remove_button": True
    }
    return render(request, "orders/cart.html", context)


@login_required(login_url="users:login")
def checkout(request):
    if request.method == "POST":
        cart_items = Cart.objects.filter(user=request.user)
        if cart_items.count() > 0:
            new_order = Order()
            new_order.user = request.user
            new_order.is_completed = False
            new_order.save()
            for cart_item in cart_items:
                order_item = OrderItem()
                order_item.order = new_order
                order_item.menu_item = cart_item.menu_item
                order_item.save()
                for topping in cart_item.toppings.all():
                    order_item.toppings.add(topping)
                for sub_addition in cart_item.sub_additions.all():
                    order_item.sub_additions.add(sub_addition)
                order_item.save()
                cart_item.delete()
            context = {
                "order_no": new_order.id
            }
            return render(request, "orders/checkout.html", context)
    context = {
        "cart_items_count": Cart.objects.filter(user=request.user).count(),
        "cart_items": Cart.objects.filter(user=request.user),
        "cart_cost": Cart.objects.filter(user=request.user).aggregate(Sum('price')),
        "remove_button": False
    }
    return render(request, "orders/payment.html", context)


@login_required(login_url="users:login")
def orders(request, order_id=None):
    context = {
        "cart_items_count": Cart.objects.filter(user=request.user).count()
    }
    if order_id is None:
        if request.method == "POST":
            form = request.POST
            order_id = form.get("order_id")
            action = form.get("action")
            _filter = form.get("filter")
            try:
                _order = Order.objects.get(pk=order_id)
            except Order.DoesNotExist:
                return HttpResponseNotFound("<h1>Order not found!</h1>")
            context['filter_sel'] = _filter
            if action == "mark_as_completed":
                _order.is_completed = True
                _order.save()
            elif action == "mark_as_pending":
                _order.is_completed = False
                _order.save()
        if request.user.is_superuser:
            context['orders'] = Order.objects.all()
        else:
            context['orders'] = Order.objects.filter(user=request.user)
        return render(request, "orders/order-list.html", context)
    else:
        try:
            _order = Order.objects.get(pk=order_id)
        except Order.DoesNotExist:
            return HttpResponseNotFound("<h1>Order not found!</h1>")
        if request.user != _order.user and not request.user.is_superuser:
            return HttpResponseNotFound("<h1>Order not found!</h1>")
        if request.method == "POST":
            form = request.POST
            action = form.get("action")
            if action == "mark_as_completed":
                _order.is_completed = True
                _order.save()
            elif action == "mark_as_pending":
                _order.is_completed = False
                _order.save()
        context['order_items'] = OrderItem.objects.filter(order=_order)
        context['order'] = _order
        return render(request, "orders/order-detail.html", context)


@require_POST
def re_order(request):
    form = request.POST
    order_id = form.get("order_id")
    try:
        _order = Order.objects.get(pk=order_id)
    except Order.DoesNotExist:
        return HttpResponseNotFound("<h1>Order not found!</h1>")
    order_items = OrderItem.objects.filter(order=_order)
    cart_items = Cart.objects.filter(user=request.user)
    for item in cart_items:
        item.delete()
    for item in order_items:
        _cart = Cart()
        _cart.user = request.user
        _cart.menu_item = item.menu_item
        _cart.price = item.menu_item.price
        _cart.save()
        for topping in item.toppings.all():
            _cart.toppings.add(topping)
        for sub_addition in item.sub_additions.all():
            _cart.sub_additions.add(sub_addition)
            _cart.price += sub_addition.price
        _cart.save()
    return redirect("orders:payment")

def faq(request):
    return render(request, "orders/faq.html")

def about(request):
    return render(request, "orders/about.html")

def contact(request):
    if request.method == 'POST':
        form = ContactForm(request.POST)
        if form.is_valid():
            form.save()
            return render(request, 'orders/contactsuccess.html')
        else:
            return render(request, 'orders/contactfailure.html')
    form = ContactForm()
    context = {'form': form}
    return render(request, 'orders/contact.html', context)

class ContactForm(ModelForm):
    class Meta:
        model = Contact
        fields = '__all__'
        
def checkoutinfo(request):
    if request.method == 'POST':
        form = CheckoutInfoForm(request.POST)
        if form.is_valid():
            form.save()
            return render(request, 'orders/order-receipt.html')
        else:
            return render(request, 'orders/order-receipt.html')
    form = CheckoutInfoForm()
    context = {'form': form}
    return render(request, 'orders/order-receipt.html', context)

class CheckoutInfoForm(ModelForm):
    class Meta:
        model = CheckoutInfo
        fields = '__all__'
        
def payment(request):
    return render (request,'orders/payment.html')
