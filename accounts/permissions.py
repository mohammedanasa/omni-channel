# from rest_framework.permissions import BasePermission


# class IsMerchantOwner(BasePermission):
#     """
#     Allow actions only if request.user is merchant.owner
#     """
#     def has_object_permission(self, request, view, obj):
#         return obj.owner == request.user


from rest_framework.permissions import BasePermission

class IsMerchantOwner(BasePermission):
    """
    Allow access only if request.user owns the Merchant.
    """

    def has_object_permission(self, request, view, obj):
        # For retrieve/update/delete actions
        return obj.owner == request.user

    def has_permission(self, request, view):
        # List and Create permitted, object check happens later
        return request.user and request.user.is_authenticated
